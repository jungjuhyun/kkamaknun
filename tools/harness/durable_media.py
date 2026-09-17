"""Crash-safe, checkpointed media-run primitives.

Only immutable journals, verified completed units, a final manifest, and a
marker-last commit receipt are durable. Local staging is intentionally not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import material_store

SCHEMA = 1
JOURNAL_RE = re.compile(r"journal/(\d{8})-([0-9a-f]{64})\.json$")


class DurableMediaError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return material_store.sha256_file(path)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".staging")
    temporary.write_bytes(canonical(value))
    os.replace(temporary, path)


def receipt_for(path: Path, key: str) -> dict[str, Any]:
    return {"key": key, "size": path.stat().st_size, "sha256": digest(path)}


class LocalObjectStore:
    """Test store; a second local workspace represents a clean device/cache."""
    def __init__(self, root: Path):
        self.root = root

    def put(self, source: Path, key: str) -> dict[str, Any]:
        target = self.root / key
        expected = receipt_for(source, key)
        if target.exists():
            verify(target, expected)
            return expected
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
        verify(target, expected)
        return expected

    def get(self, receipt: dict[str, Any], target: Path) -> None:
        source = self.root / receipt["key"]
        temporary = target.with_suffix(target.suffix + ".partial")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, temporary)
        verify(temporary, receipt)
        os.replace(temporary, target)

    def keys(self, prefix: str) -> list[str]:
        base = self.root / prefix
        return [] if not base.exists() else sorted(
            p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file()
        )


class RcloneObjectStore:
    """Provider-neutral rclone adapter; credentials remain outside the repo."""
    def __init__(self, remote_root: str | None = None):
        self.remote_root = remote_root or material_store.remote_root_from_env()

    def remote(self, key: str) -> str:
        return material_store.remote_path_for_key(key, self.remote_root)

    def put(self, source: Path, key: str) -> dict[str, Any]:
        expected = receipt_for(source, key)
        material_store._run_rclone(["copyto", str(source), self.remote(key), "--check-first", "--checksum"])
        with tempfile.TemporaryDirectory() as temporary:
            self.get(expected, Path(temporary) / "roundtrip.bin")
        return expected

    def get(self, receipt: dict[str, Any], target: Path) -> None:
        temporary = target.with_suffix(target.suffix + ".partial")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        material_store._run_rclone(["copyto", self.remote(receipt["key"]), str(temporary), "--check-first", "--checksum"])
        verify(temporary, receipt)
        os.replace(temporary, target)

    def keys(self, prefix: str) -> list[str]:
        proc = subprocess.run(
            [material_store.rclone_executable(), "lsf", self.remote(prefix), "--recursive"],
            text=True, capture_output=True, check=False,
        )
        if proc.returncode:
            if "directory not found" in (proc.stdout + proc.stderr).lower():
                return []
            raise DurableMediaError(f"rclone list failed: {proc.stdout}{proc.stderr}")
        return sorted(f"{prefix.rstrip('/')}/{line.strip()}" for line in proc.stdout.splitlines() if line.strip())


def verify(path: Path, receipt: dict[str, Any]) -> None:
    if not path.is_file():
        raise DurableMediaError(f"receipt verification failed: {path}")
    if receipt.get("size") is not None and path.stat().st_size != receipt["size"]:
        raise DurableMediaError(f"receipt verification failed: {path}")
    if receipt.get("sha256") and digest(path) != receipt["sha256"]:
        raise DurableMediaError(f"receipt verification failed: {path}")


def validate_media(path: Path, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg") -> None:
    probe = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True)
    try:
        streams = json.loads(probe.stdout).get("streams")
    except json.JSONDecodeError:
        streams = None
    if probe.returncode or not streams:
        raise DurableMediaError(f"ffprobe failed: {path}")
    decode = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0", "-f", "null", "-"], capture_output=True, text=True)
    if decode.returncode:
        raise DurableMediaError(f"full decode failed: {path}")


def read_journal(store: Any, workspace: Path, run_id: str) -> dict[str, Any]:
    prefix = f"runs/{run_id}/"
    candidates: list[tuple[int, str, str]] = []
    for key in store.keys(prefix + "journal"):
        match = JOURNAL_RE.search(key)
        if not match:
            raise DurableMediaError(f"invalid journal key: {key}")
        candidates.append((int(match.group(1)), match.group(2), key))
    if not candidates:
        raise DurableMediaError(f"no durable journal: {run_id}")
    generation, expected_hash, key = sorted(candidates)[-1]
    local = workspace / "recovered.json"
    store.get({"key": key, "size": None, "sha256": expected_hash}, local)
    state = json.loads(local.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA or state.get("run_id") != run_id or state.get("generation") != generation:
        raise DurableMediaError("invalid journal contents")
    return state


class Run:
    def __init__(self, store: Any, workspace: Path, state: dict[str, Any], holder: str | None = None):
        self.store, self.workspace, self.state = store, workspace, state
        self.holder = str(state.get("lease", {}).get("holder", "")) if holder is None else holder

    @property
    def prefix(self) -> str:
        return f"runs/{self.state['run_id']}"

    def _ensure_live_lease(self, *, allow_committed: bool = False) -> None:
        lease = self.state.get("lease", {})
        if self.state.get("state") == "COMMITTED" and not allow_committed:
            raise DurableMediaError("committed run is immutable")
        if lease.get("holder") != self.holder:
            raise DurableMediaError("run lease is not held by this process")

    def save(self) -> None:
        self._ensure_live_lease(allow_committed=True)
        latest = read_journal(self.store, self.workspace / "lease_check", self.state["run_id"])
        latest_lease = latest.get("lease", {})
        if latest["generation"] > self.state["generation"] and latest_lease.get("holder") != self.holder:
            raise DurableMediaError("concurrent or stale run lease")
        self.state["generation"] += 1
        self.state["updated_at"] = time.time()
        self.state["lease"]["heartbeat"] = self.state["updated_at"]
        local = self.workspace / "journal.json"
        write_json(local, self.state)
        checksum = digest(local)
        key = f"{self.prefix}/journal/{self.state['generation']:08d}-{checksum}.json"
        receipt = self.store.put(local, key)
        verify(local, receipt)

    def checkpoint(self, unit: str, file: Path, *, media: bool = False) -> None:
        self._ensure_live_lease()
        if media:
            validate_media(file)
        file_hash = digest(file)
        receipt = self.store.put(file, f"{self.prefix}/checkpoints/{unit}/{file_hash}.mp4")
        verify(file, receipt)
        self.state["units"][unit] = {
            "state": "CHECKPOINTED", "receipt": receipt,
            "input_identity": self.state["input_identity"],
            "config_sha256": self.state["config_sha256"],
        }
        self.save()

    def render(self, unit: str, command: list[str]) -> Path:
        """A failed process may leave staging bytes, but never a unit checkpoint."""
        self._ensure_live_lease()
        reusable = self.workspace / "units" / f"{unit}.mp4"
        if self.restore_unit(unit, reusable):
            return reusable
        target = self.workspace / "staging" / f"{unit}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = [part.replace("{output}", str(target)) for part in command]
        if subprocess.run(rendered, capture_output=True, text=True).returncode:
            raise DurableMediaError(f"unit render failed: {unit}")
        self.checkpoint(unit, target, media=True)
        return target

    def restore_unit(self, unit: str, target: Path) -> bool:
        entry = self.state["units"].get(unit)
        if not entry or entry.get("state") != "CHECKPOINTED":
            return False
        if entry.get("input_identity") != self.state["input_identity"] or entry.get("config_sha256") != self.state["config_sha256"]:
            raise DurableMediaError(f"checkpoint identity mismatch: {unit}")
        self.store.get(entry["receipt"], target)
        return True

    def publish_final(self, final: Path) -> None:
        """Publish final + manifest, but deliberately do not mark it committed."""
        self._ensure_live_lease()
        validate_media(final)
        final_hash = digest(final)
        final_receipt = self.store.put(final, f"{self.prefix}/committed/{final_hash}.mp4")
        manifest = {
            "schema": SCHEMA, "run_id": self.state["run_id"], "final": final_receipt,
            "input_identity": self.state["input_identity"], "config_sha256": self.state["config_sha256"],
            "units": self.state["units"], "validation": {"ffprobe": "PASS", "full_decode": "PASS"},
        }
        local_manifest = self.workspace / "manifest.json"
        write_json(local_manifest, manifest)
        manifest_hash = digest(local_manifest)
        manifest_receipt = self.store.put(local_manifest, f"{self.prefix}/manifests/{manifest_hash}.json")
        self.state.update({"state": "VALIDATED", "final": final_receipt, "manifest": manifest_receipt})
        self.save()

    def finalize_commit(self) -> None:
        """Explicit marker-last transition; safe after a fresh recovery."""
        if self.state.get("state") == "COMMITTED":
            return
        self._ensure_live_lease()
        if self.state.get("state") != "VALIDATED" or not self.state.get("final") or not self.state.get("manifest"):
            raise DurableMediaError("validated final and manifest required before marker")
        verified = self.workspace / "commit_verify.mp4"
        self.store.get(self.state["final"], verified)
        validate_media(verified)
        verified_manifest = self.workspace / "commit_manifest.json"
        self.store.get(self.state["manifest"], verified_manifest)
        manifest = json.loads(verified_manifest.read_text(encoding="utf-8"))
        if manifest.get("final") != self.state["final"] or manifest.get("run_id") != self.state["run_id"]:
            raise DurableMediaError("final manifest mismatch")
        marker = {"schema": SCHEMA, "run_id": self.state["run_id"], "final": self.state["final"], "manifest": self.state["manifest"]}
        local_marker = self.workspace / "commit.json"
        write_json(local_marker, marker)
        marker_receipt = self.store.put(local_marker, f"{self.prefix}/COMMITTED.json")
        self.state.update({"state": "COMMITTED", "commit_marker": marker_receipt})
        self.save()

    def commit(self, final: Path) -> None:
        """Compatibility wrapper for a complete validated marker-last commit."""
        self.publish_final(final)
        self.finalize_commit()

    def assemble(self, units: list[str], final: Path, *, ffmpeg: str = "ffmpeg") -> None:
        self._ensure_live_lease()
        lines = []
        for unit in units:
            local = self.workspace / "assemble" / f"{unit}.mp4"
            if not self.restore_unit(unit, local):
                raise DurableMediaError(f"missing checkpoint: {unit}")
            lines.append("file '" + local.resolve().as_posix().replace("'", "'\\''") + "'")
        listing = self.workspace / "assemble" / "concat.txt"
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text("\n".join(lines), encoding="utf-8")
        staging = final.with_name(final.stem + ".staging" + final.suffix)
        if subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(staging)], capture_output=True, text=True).returncode:
            raise DurableMediaError("final mux failed")
        validate_media(staging, ffmpeg=ffmpeg)
        os.replace(staging, final)
        self.publish_final(final)
        self.finalize_commit()

    def rollback(self) -> None:
        self._ensure_live_lease()
        self.state["state"] = "ABANDONED"
        self.save()


def create(store: Any, workspace: Path, input_identity: dict[str, Any], config: dict[str, Any], run_id: str | None = None, *, lease_seconds: float = 60.0) -> Run:
    identifier = run_id or str(uuid.uuid4())
    if store.keys(f"runs/{identifier}"):
        raise DurableMediaError(f"run already exists: {identifier}")
    holder = str(uuid.uuid4())
    now = time.time()
    state = {
        "schema": SCHEMA, "run_id": identifier, "state": "RUNNING", "generation": 1,
        "created_at": now, "updated_at": now, "input_identity": input_identity,
        "config_sha256": hashlib.sha256(canonical(config)).hexdigest(), "units": {},
        "lease": {"holder": holder, "heartbeat": now, "seconds": lease_seconds},
    }
    run = Run(store, workspace, state, holder)
    local = workspace / "journal.json"
    write_json(local, state)
    checksum = digest(local)
    store.put(local, f"runs/{identifier}/journal/{state['generation']:08d}-{checksum}.json")
    return run


def recover(store: Any, workspace: Path, run_id: str, *, takeover: bool = False) -> Run:
    state = read_journal(store, workspace, run_id)
    marker_keys = [key for key in store.keys(f"runs/{run_id}") if key == f"runs/{run_id}/COMMITTED.json"]
    if marker_keys:
        marker_path = workspace / "marker.json"
        store.get({"key": marker_keys[0], "size": None, "sha256": None}, marker_path)
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("run_id") != run_id or not marker.get("final") or not marker.get("manifest"):
            raise DurableMediaError("invalid commit marker")
        final = workspace / "recovered_final.mp4"
        store.get(marker["final"], final)
        validate_media(final)
        state.update({"state": "COMMITTED", "final": marker["final"], "manifest": marker["manifest"]})
        return Run(store, workspace, state, state.get("lease", {}).get("holder"))
    if state.get("state") == "COMMITTED":
        raise DurableMediaError("committed journal has no marker")
    lease = state.get("lease", {})
    age = time.time() - float(lease.get("heartbeat", 0))
    if age <= float(lease.get("seconds", 0)):
        if takeover:
            raise DurableMediaError("active run lease; wait for expiry before explicit takeover")
        # Inspection and verified checkpoint materialization are safe, but this
        # handle deliberately has no mutation lease.
        return Run(store, workspace, state, holder="")
    if not takeover:
        raise DurableMediaError("stale run requires explicit takeover")
    holder = str(uuid.uuid4())
    state["lease"] = {"holder": holder, "heartbeat": time.time(), "seconds": lease.get("seconds", 60.0)}
    state["state"] = "RECOVERING" if state.get("state") == "RUNNING" else state.get("state")
    run = Run(store, workspace, state, holder)
    run.save()
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--local-store")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--input-json", required=True)
    start.add_argument("--config-json", required=True)
    start.add_argument("--run-id")
    for name in ("status", "recover", "rollback", "finalize"):
        command = sub.add_parser(name)
        command.add_argument("run_id")
        if name == "recover":
            command.add_argument("--takeover", action="store_true")
    args = parser.parse_args(argv)
    store = LocalObjectStore(Path(args.local_store)) if args.local_store else RcloneObjectStore()
    workspace = Path(args.workspace)
    if args.command == "start":
        run = create(store, workspace, json.loads(Path(args.input_json).read_text()), json.loads(Path(args.config_json).read_text()), args.run_id)
        print(run.state["run_id"])
        return 0
    if args.command == "status":
        print(json.dumps(read_journal(store, workspace, args.run_id), ensure_ascii=False, indent=2))
        return 0
    run = recover(store, workspace, args.run_id, takeover=getattr(args, "takeover", False))
    if args.command == "rollback":
        run.rollback()
    elif args.command == "finalize":
        run.finalize_commit()
    print(json.dumps(run.state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
