"""Provider-neutral external material helper.

This module deliberately stores no credentials and owns no project truth.
Artifact metadata is read from ``tools/harness/STATE.json`` after logical-ID
cutover. During migration, ``--object-key`` can be used without changing the
current runtime contract.

Environment:
    KKAMAKNUN_MATERIAL_ROOT
        Local material/cache root. Required for artifact-ID path resolution
        unless --local is supplied.
    KKAMAKNUN_MATERIAL_REMOTE
        rclone remote root, e.g. ``remote:kkamaknun_external``.
        Required only for materialize/publish.
    KKAMAKNUN_RCLONE
        Optional rclone executable/path. Defaults to ``rclone``.

Examples after cutover:
    python tools/harness/material_store.py list
    python tools/harness/material_store.py path ep1.primary_recording
    python tools/harness/material_store.py verify ep1.primary_recording
    python tools/harness/material_store.py materialize ep1.primary_recording

Migration-only direct key:
    python tools/harness/material_store.py publish \
        --object-key source/ep1/example.mp4 --local X:/source/ep1/example.mp4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_STATE = HERE / "STATE.json"

ENV_LOCAL_ROOT = "KKAMAKNUN_MATERIAL_ROOT"
ENV_REMOTE_ROOT = "KKAMAKNUN_MATERIAL_REMOTE"
ENV_RCLONE = "KKAMAKNUN_RCLONE"


class MaterialStoreError(RuntimeError):
    pass


def _stdout_utf8() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8", errors="replace")


def load_state(path: Path = DEFAULT_STATE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_artifacts(path: Path = DEFAULT_STATE) -> dict[str, dict[str, Any]]:
    state = load_state(path)
    external = state.get("external_material")
    if not isinstance(external, dict):
        raise MaterialStoreError(
            "STATE.json has no external_material registry yet; "
            "use --object-key during migration or complete logical-ID cutover."
        )
    artifacts = external.get("artifacts")
    if not isinstance(artifacts, dict):
        raise MaterialStoreError("external_material.artifacts is missing or invalid")
    return artifacts


def normalize_object_key(raw: str) -> str:
    key = PurePosixPath(raw)
    if key.is_absolute() or ".." in key.parts:
        raise MaterialStoreError(f"unsafe object key: {raw!r}")
    normalized = key.as_posix().lstrip("./")
    if not normalized or normalized == ".":
        raise MaterialStoreError("object key must not be empty")
    return normalized


def local_root_from_env() -> Path:
    raw = os.environ.get(ENV_LOCAL_ROOT)
    if not raw:
        raise MaterialStoreError(f"{ENV_LOCAL_ROOT} is not set")
    return Path(raw).expanduser()


def remote_root_from_env() -> str:
    raw = os.environ.get(ENV_REMOTE_ROOT, "").strip()
    if not raw:
        raise MaterialStoreError(f"{ENV_REMOTE_ROOT} is not set")
    return raw.rstrip("/")


def rclone_executable() -> str:
    return os.environ.get(ENV_RCLONE, "rclone")


def local_path_for_key(object_key: str, root: Path | None = None) -> Path:
    key = PurePosixPath(normalize_object_key(object_key))
    base = root if root is not None else local_root_from_env()
    return base.joinpath(*key.parts)


def remote_path_for_key(object_key: str, remote_root: str | None = None) -> str:
    base = (remote_root or remote_root_from_env()).rstrip("/")
    return f"{base}/{normalize_object_key(object_key)}"


def artifact_record(
    artifact_id: str, state_path: Path = DEFAULT_STATE
) -> dict[str, Any]:
    artifacts = load_artifacts(state_path)
    try:
        record = artifacts[artifact_id]
    except KeyError as exc:
        raise MaterialStoreError(f"unknown artifact id: {artifact_id}") from exc
    if not isinstance(record, dict):
        raise MaterialStoreError(f"invalid artifact record: {artifact_id}")
    if "object_key" not in record:
        raise MaterialStoreError(f"artifact has no object_key: {artifact_id}")
    return record


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_path(path: Path, record: dict[str, Any] | None = None) -> list[str]:
    record = record or {}
    kind = record.get("kind", "file")
    problems: list[str] = []

    if kind == "directory":
        if not path.is_dir():
            problems.append(f"directory missing: {path}")
        return problems

    if not path.is_file():
        problems.append(f"file missing: {path}")
        return problems

    expected_size = record.get("size")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        problems.append(
            f"size mismatch: expected={expected_size} actual={path.stat().st_size}"
        )

    expected_sha = record.get("sha256")
    if expected_sha:
        actual = sha256_file(path)
        if actual.lower() != str(expected_sha).lower():
            problems.append(
                f"sha256 mismatch: expected={expected_sha} actual={actual}"
            )
    return problems


def _run_rclone(args: list[str]) -> None:
    exe = rclone_executable()
    if shutil.which(exe) is None and not Path(exe).exists():
        raise MaterialStoreError(
            f"rclone executable not found: {exe!r}; "
            f"install rclone or set {ENV_RCLONE}"
        )
    proc = subprocess.run(
        [exe, *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise MaterialStoreError(
            f"rclone failed ({proc.returncode}): {' '.join(args)}\n{proc.stdout}"
        )


def materialize(
    *,
    object_key: str,
    local_path: Path,
    record: dict[str, Any] | None = None,
) -> None:
    record = record or {}
    kind = record.get("kind", "file")

    if local_path.exists():
        problems = verify_path(local_path, record)
        if not problems:
            return
        raise MaterialStoreError(
            "existing local artifact failed verification; refusing overwrite:\n"
            + "\n".join(problems)
        )

    remote = remote_path_for_key(object_key)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    if kind == "directory":
        local_path.mkdir(parents=True, exist_ok=True)
        _run_rclone(["copy", remote, str(local_path), "--check-first", "--checksum"])
    else:
        _run_rclone(
            ["copyto", remote, str(local_path), "--check-first", "--checksum"]
        )

    problems = verify_path(local_path, record)
    if problems:
        raise MaterialStoreError(
            "materialized artifact failed local verification:\n"
            + "\n".join(problems)
        )


def publish(
    *,
    object_key: str,
    local_path: Path,
    record: dict[str, Any] | None = None,
    force: bool = False,
) -> None:
    record = record or {}
    if record and not record.get("publish", False) and not force:
        raise MaterialStoreError(
            "artifact is not publish-enabled; use --force only for an approved migration"
        )

    problems = verify_path(local_path, record)
    if problems:
        raise MaterialStoreError(
            "local artifact failed verification; refusing publish:\n"
            + "\n".join(problems)
        )

    remote = remote_path_for_key(object_key)
    kind = record.get("kind", "file")
    if kind == "directory":
        _run_rclone(["copy", str(local_path), remote, "--check-first", "--checksum"])
    else:
        _run_rclone(
            ["copyto", str(local_path), remote, "--check-first", "--checksum"]
        )


def resolve_inputs(args: argparse.Namespace) -> tuple[str, Path, dict[str, Any]]:
    if args.object_key:
        key = normalize_object_key(args.object_key)
        record: dict[str, Any] = {"kind": args.kind}
    else:
        if not args.artifact_id:
            raise MaterialStoreError("artifact id or --object-key is required")
        record = artifact_record(args.artifact_id, Path(args.state))
        key = normalize_object_key(str(record["object_key"]))

    if args.local:
        local = Path(args.local).expanduser()
    else:
        local = local_path_for_key(key)
    return key, local, record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE),
        help="runtime STATE.json containing external_material.artifacts",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list logical artifact IDs from STATE.json")

    for name in ("path", "verify", "materialize", "publish"):
        cmd = sub.add_parser(name)
        cmd.add_argument("artifact_id", nargs="?")
        cmd.add_argument("--object-key")
        cmd.add_argument("--local")
        cmd.add_argument(
            "--kind", choices=("file", "directory"), default="file",
            help="migration-only kind when --object-key is used",
        )
        if name == "publish":
            cmd.add_argument(
                "--force",
                action="store_true",
                help="allow migration publish without publish-enabled registry entry",
            )

    return parser


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            for artifact_id in sorted(load_artifacts(Path(args.state))):
                print(artifact_id)
            return 0

        key, local, record = resolve_inputs(args)

        if args.command == "path":
            print(local)
            return 0

        if args.command == "verify":
            problems = verify_path(local, record)
            if problems:
                for problem in problems:
                    print(f"FAIL — {problem}")
                return 1
            print(f"PASS — {local}")
            return 0

        if args.command == "materialize":
            materialize(object_key=key, local_path=local, record=record)
            print(f"PASS — materialized {key} -> {local}")
            return 0

        if args.command == "publish":
            publish(
                object_key=key,
                local_path=local,
                record=record,
                force=args.force,
            )
            print(f"PASS — published {local} -> {key}")
            return 0

        parser.error(f"unknown command: {args.command}")
    except (OSError, json.JSONDecodeError, MaterialStoreError) as exc:
        print(f"FAIL — {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
