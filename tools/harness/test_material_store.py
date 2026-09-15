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
