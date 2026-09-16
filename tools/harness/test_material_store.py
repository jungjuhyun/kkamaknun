import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import material_store


class MaterialStoreTests(unittest.TestCase):
    def test_normalize_object_key_rejects_parent(self):
        with self.assertRaises(material_store.MaterialStoreError):
            material_store.normalize_object_key("../secret")

    def test_local_path_uses_posix_object_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = material_store.local_path_for_key(
                "source/ep1/example.mp4", root=root
            )
            self.assertEqual(
                path, root / "source" / "ep1" / "example.mp4"
            )

    def test_remote_path_join(self):
        self.assertEqual(
            material_store.remote_path_for_key(
                "review/EP1.mp4", remote_root="drive:kkamaknun_external/"
            ),
            "drive:kkamaknun_external/review/EP1.mp4",
        )

    def test_load_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "STATE.json"
            state.write_text(
                json.dumps(
                    {
                        "external_material": {
                            "artifacts": {
                                "ep1.primary_recording": {
                                    "object_key": "source/ep1/a.mp4",
                                    "kind": "file",
                                }
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            artifacts = material_store.load_artifacts(state)
            self.assertIn("ep1.primary_recording", artifacts)

    def test_runtime_registry_has_required_ep1_logical_ids(self):
        artifacts = material_store.load_artifacts()
        expected = {
            "ep1.primary_recording",
            "ep1.source_subtitles_ko",
            "ep1.desktop_transcript",
            "ep1.mic_transcript",
            "ep1.sync_timeline_jsonl",
            "ep1.sync_timeline_csv",
            "ep1.narrative_map",
            "ep1.transcription_qa",
            "ep1.new_scene_pool",
            "ep1.review_b",
            "ep1.review_c",
        }
        self.assertTrue(expected.issubset(artifacts))

    def test_primary_record_uses_verified_immutable_facts(self):
        record = material_store.artifact_record("ep1.primary_recording")
        self.assertEqual(record["object_key"], "source/ep1/2026-09-06 23-54-01-01.mp4")
        self.assertEqual(record["size"], 5_065_619_726)
        self.assertEqual(
            record["sha256"],
            "7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525",
        )
        self.assertFalse(record["publish"])

    def test_registry_resolves_primary_to_local_cache_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {material_store.ENV_LOCAL_ROOT: tmp},
                clear=False,
            ):
                key, local, record = material_store.resolve_inputs(
                    type("Args", (), {
                        "object_key": None,
                        "artifact_id": "ep1.primary_recording",
                        "state": str(material_store.DEFAULT_STATE),
                        "local": None,
                        "kind": "file",
                    })()
                )
            self.assertEqual(key, "source/ep1/2026-09-06 23-54-01-01.mp4")
            self.assertEqual(local, Path(tmp) / "source" / "ep1" / "2026-09-06 23-54-01-01.mp4")
            self.assertFalse(record["publish"])

    def test_registry_derived_artifact_publish_uses_its_object_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "EP1_NARRATIVE_MAP.md"
            local.write_text("evidence", encoding="utf-8")
            record = material_store.artifact_record("ep1.narrative_map")
            with patch.object(material_store, "remote_path_for_key", return_value="remote:root/transcription/EP1_NARRATIVE_MAP.md"), patch.object(material_store, "_run_rclone") as run:
                material_store.publish(
                    object_key=record["object_key"], local_path=local, record=record
                )
            run.assert_called_once_with([
                "copyto", str(local), "remote:root/transcription/EP1_NARRATIVE_MAP.md", "--check-first", "--checksum"
            ])

    def test_verify_file_size_and_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            payload = b"abc"
            path.write_bytes(payload)
            record = {
                "kind": "file",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            self.assertEqual(material_store.verify_path(path, record), [])

    def test_existing_invalid_materialize_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"wrong")
            with self.assertRaises(material_store.MaterialStoreError):
                material_store.materialize(
                    object_key="source/x.bin",
                    local_path=path,
                    record={"kind": "file", "size": 999},
                )

    def test_publish_disabled_by_default_for_registry_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"abc")
            with self.assertRaises(material_store.MaterialStoreError):
                material_store.publish(
                    object_key="review/x.bin",
                    local_path=path,
                    record={"kind": "file", "publish": False},
                )

    def test_local_root_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {material_store.ENV_LOCAL_ROOT: tmp},
                clear=False,
            ):
                self.assertEqual(
                    material_store.local_path_for_key("a/b"),
                    Path(tmp) / "a" / "b",
                )


if __name__ == "__main__":
    unittest.main()
