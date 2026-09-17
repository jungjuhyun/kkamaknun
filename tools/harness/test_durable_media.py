import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import durable_media


def make_media(path: Path) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
        "-c:v", "libx264", "-c:a", "aac", str(path),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class FailAfterCheckpointUpload:
    """Leaves an unreferenced remote object exactly like a publish interruption."""
    def __init__(self, inner): self.inner = inner
    def put(self, source, key):
        receipt = self.inner.put(source, key)
        if "/checkpoints/" in key:
            raise durable_media.DurableMediaError("injected checkpoint publish interruption")
        return receipt
    def get(self, receipt, target): return self.inner.get(receipt, target)
    def keys(self, prefix): return self.inner.keys(prefix)


class DurableMediaTests(unittest.TestCase):
    def test_checkpoint_recovery_and_cross_cache_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "a", {"source": {"sha256": "x"}}, {"codec": "h264"}, "run-1")
            source = root / "unit.mp4"; source.write_bytes(b"checkpoint")
            run.checkpoint("u1", source)
            recovered = durable_media.recover(store, root / "b", "run-1")
            target = root / "b" / "u1.mp4"
            self.assertTrue(recovered.restore_unit("u1", target))
            self.assertEqual(target.read_bytes(), b"checkpoint")
            self.assertEqual(recovered.state["input_identity"]["source"]["sha256"], "x")

    def test_generation_is_append_only_and_bad_journal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "a", {}, {}, "run-2")
            self.assertGreaterEqual(len(store.keys("runs/run-2/journal")), 1)
            bad = root / "cloud" / "runs/run-2/journal/99999999.json"; bad.parent.mkdir(parents=True, exist_ok=True); bad.write_text(json.dumps({"schema": 9}), encoding="utf-8")
            with self.assertRaises(durable_media.DurableMediaError): durable_media.recover(store, root / "b", "run-2")

    def test_corrupt_checkpoint_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "a", {}, {}, "run-3")
            source = root / "unit.mp4"; source.write_bytes(b"ok"); run.checkpoint("u", source)
            receipt = run.state["units"]["u"]["receipt"]; (root / "cloud" / receipt["key"]).write_bytes(b"bad")
            with self.assertRaises(durable_media.DurableMediaError): run.restore_unit("u", root / "out.mp4")

    def test_real_media_commit_requires_validation_then_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            media = root / "final.mp4"
            make_media(media)
            run = durable_media.create(store, root / "work", {"source": "immutable"}, {}, "run-4")
            self.assertNotIn("COMMITTED.json", " ".join(store.keys("runs/run-4")))
            run.commit(media)
            self.assertEqual(run.state["state"], "COMMITTED")
            self.assertIn("runs/run-4/COMMITTED.json", store.keys("runs/run-4"))

    def test_render_kill_boundary_and_assemble_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "work", {}, {}, "run-5")
            with self.assertRaises(durable_media.DurableMediaError):
                run.render("u", ["ffmpeg", "-f", "lavfi", "-i", "not-a-filter", "{output}"])
            self.assertNotIn("u", run.state["units"])
            run.render("u", ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "libx264", "-c:a", "aac", "{output}"])
            run.assemble(["u"], root / "out.mp4")
            self.assertEqual(run.state["state"], "COMMITTED")

    def test_a_render_interruption_rerenders_only_missing_unit_after_takeover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "work", {"source": "immutable"}, {}, "a", lease_seconds=0)
            with self.assertRaises(durable_media.DurableMediaError):
                run.render("u", ["ffmpeg", "-f", "lavfi", "-i", "not-a-filter", "{output}"])
            resumed = durable_media.recover(store, root / "new-process", "a", takeover=True)
            resumed.render("u", ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "libx264", "-c:a", "aac", "{output}"])
            self.assertEqual(resumed.state["units"]["u"]["state"], "CHECKPOINTED")

    def test_b_checkpoint_publish_interruption_does_not_create_reusable_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inner = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(FailAfterCheckpointUpload(inner), root / "work", {}, {}, "b", lease_seconds=0)
            source = root / "u.mp4"; source.write_bytes(b"unit")
            with self.assertRaises(durable_media.DurableMediaError):
                run.checkpoint("u", source)
            resumed = durable_media.recover(inner, root / "new-process", "b", takeover=True)
            self.assertFalse(resumed.restore_unit("u", root / "out.mp4"))
            self.assertTrue(any("/checkpoints/u/" in key for key in inner.keys("runs/b")))

    def test_c_mux_interruption_never_creates_commit_marker_and_reuses_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "work", {}, {}, "c", lease_seconds=0)
            unit = root / "u.mp4"; make_media(unit); run.checkpoint("u", unit, media=True)
            with patch.object(durable_media.subprocess, "run", return_value=type("Result", (), {"returncode": 1})()):
                with self.assertRaises(durable_media.DurableMediaError):
                    run.assemble(["u"], root / "final.mp4")
            self.assertNotIn("runs/c/COMMITTED.json", store.keys("runs/c"))
            resumed = durable_media.recover(store, root / "new-process", "c", takeover=True)
            self.assertTrue(resumed.restore_unit("u", root / "new-process" / "u.mp4"))

    def test_d_prevalidation_failure_has_no_final_or_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            run = durable_media.create(store, root / "work", {}, {}, "d", lease_seconds=0)
            broken = root / "broken.mp4"; broken.write_bytes(b"not media")
            with self.assertRaises(durable_media.DurableMediaError):
                run.publish_final(broken)
            self.assertNotIn("final", run.state)
            self.assertFalse(any("/committed/" in key or key.endswith("COMMITTED.json") for key in store.keys("runs/d")))
            self.assertEqual(durable_media.recover(store, root / "new-process", "d", takeover=True).state["input_identity"], {})

    def test_e_validated_final_requires_explicit_marker_resume_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            final = root / "final.mp4"; make_media(final)
            run = durable_media.create(store, root / "work", {"sha256": "immutable"}, {}, "e", lease_seconds=0)
            run.publish_final(final)
            keys_before = store.keys("runs/e")
            self.assertTrue(any("/committed/" in key for key in keys_before))
            self.assertTrue(any("/manifests/" in key for key in keys_before))
            self.assertNotIn("runs/e/COMMITTED.json", keys_before)
            resumed = durable_media.recover(store, root / "new-process", "e", takeover=True)
            self.assertEqual(resumed.state["state"], "VALIDATED")
            resumed.finalize_commit()
            committed = durable_media.recover(store, root / "clean-cache", "e")
            self.assertEqual(committed.state["state"], "COMMITTED")

    def test_duplicate_run_and_active_or_stale_lease_are_distinguished(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = durable_media.LocalObjectStore(root / "cloud")
            active = durable_media.create(store, root / "active", {}, {}, "lease", lease_seconds=60)
            with self.assertRaises(durable_media.DurableMediaError):
                durable_media.create(store, root / "again", {}, {}, "lease")
            observer = durable_media.recover(store, root / "observer", "lease")
            with self.assertRaises(durable_media.DurableMediaError):
                observer.checkpoint("u", root / "missing.mp4")
            with self.assertRaises(durable_media.DurableMediaError):
                durable_media.recover(store, root / "takeover", "lease", takeover=True)
            stale = durable_media.create(store, root / "stale", {}, {}, "stale", lease_seconds=0)
            with self.assertRaises(durable_media.DurableMediaError):
                durable_media.recover(store, root / "not-explicit", "stale")
            resumed = durable_media.recover(store, root / "explicit", "stale", takeover=True)
            self.assertNotEqual(resumed.holder, stale.holder)

    def test_rclone_empty_prefix_is_a_valid_new_run_namespace(self):
        store = durable_media.RcloneObjectStore("remote:synthetic")
        result = type("Result", (), {"returncode": 1, "stdout": "", "stderr": "directory not found"})()
        with patch.object(durable_media.subprocess, "run", return_value=result):
            self.assertEqual(store.keys("runs/new"), [])


if __name__ == "__main__": unittest.main()
