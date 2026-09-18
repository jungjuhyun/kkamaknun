import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gemini_transcribe as gt


class FakeStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, source: Path, key: str):
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return {
            "key": key,
            "size": target.stat().st_size,
            "sha256": gt.material_store.sha256_file(target),
        }

    def get(self, receipt, target: Path):
        source = self.root / receipt["key"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    def keys(self, prefix: str):
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(
            p.relative_to(self.root).as_posix()
            for p in base.rglob("*")
            if p.is_file()
        )


class FakeRun:
    def __init__(self, store: FakeStore):
        self.store = store
        self.state = {
            "run_id": "run-1",
            "input_identity": {"sha256": "source"},
            "config_sha256": "config-hash",
            "units": {},
            "lease": {"holder": "holder", "seconds": 900.0},
            "state": "RUNNING",
        }
        self.holder = "holder"
        self.saves = 0

    @property
    def prefix(self):
        return "runs/run-1"

    def save(self):
        self.saves += 1


class FakeAnnotation:
    def __init__(self, text, start, end):
        self.type = "word_info"
        self.text = text
        self.speaker = None
        self.start_offset = start
        self.end_offset = end


class FakeInteraction:
    def __init__(self, text="hello", annotations=None):
        self.id = "interactions/1"
        self.output_text = text
        content = SimpleNamespace(annotations=annotations or [])
        self.steps = [SimpleNamespace(content=[content])]

    def model_dump(self, **_kwargs):
        return {"id": self.id, "output_text": self.output_text}


class FakeFiles:
    def __init__(self):
        self.uploads = 0
        self.deletes = 0

    def upload(self, file):
        self.uploads += 1
        return SimpleNamespace(
            name=f"files/{self.uploads}", uri=f"uri://{self.uploads}", mime_type="audio/flac"
        )

    def delete(self, name):
        self.deletes += 1


class FakeInteractions:
    def __init__(self, result=None, error=None):
        self.result = result or FakeInteraction()
        self.error = error
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, interaction=None, error=None):
        self.files = FakeFiles()
        self.interactions = FakeInteractions(interaction, error)


class GeminiTranscribeTests(unittest.TestCase):
    def tracks(self):
        return [
            {"stream_index": 2, "role": "desktop/source"},
            {"stream_index": 3, "role": "mic/user"},
        ]

    def test_workspace_inside_repository_is_rejected(self):
        with self.assertRaises(gt.TranscriptionError):
            gt.ensure_external_workspace(gt.HERE / "generated")

    def test_runtime_contract_routes_to_cleanroom_runner(self):
        state = json.loads((Path(__file__).parent / "STATE.json").read_text(encoding="utf-8"))
        contract = state["cleanroom_transcription_run"]
        runner = contract["runner"]
        self.assertEqual(runner["path"], "tools/harness/gemini_transcribe.py")
        self.assertEqual(runner["dependency_file"], "tools/harness/requirements_gemini.txt")
        self.assertEqual(runner["model"], "gemini-3.5-transcribe")
        self.assertEqual(runner["mode"], "verbatim")
        self.assertFalse(runner["word_timestamps_default"])
        self.assertEqual(runner["default_overlap_seconds"], 0)
        self.assertIn("--max-new-units 2", runner["preflight"])
        self.assertIn("AMBIGUOUS", contract["checkpoint_contract"]["ambiguous_paid_request"])

    def test_units_interleave_tracks_and_cover_full_timeline(self):
        units = gt.build_units(1900.0, self.tracks(), 900.0)
        self.assertEqual([u["stream_index"] for u in units[:4]], [2, 3, 2, 3])
        coverage = gt.validate_plan_coverage(units, self.tracks(), 1900.0)
        self.assertEqual(coverage["status"], "PASS")
        self.assertEqual(coverage["tracks"]["2"]["end"], 1900.0)
        self.assertEqual(coverage["tracks"]["3"]["gaps"], 0)

    def test_preflight_scope_is_first_planned_units_even_when_reused(self):
        units = gt.build_units(1900.0, self.tracks(), 900.0)
        scoped = gt.selected_run_units(units, 2)
        self.assertEqual([u["unit_id"] for u in scoped], [u["unit_id"] for u in units[:2]])
        self.assertEqual([u["stream_index"] for u in scoped], [2, 3])
        self.assertEqual(gt.selected_run_units(units, 0), units)

    def test_overlap_requires_word_timestamps_for_deterministic_ownership(self):
        with self.assertRaises(gt.TranscriptionError):
            gt.build_units(100.0, self.tracks(), 60.0, overlap_seconds=2.0)
        units = gt.build_units(
            100.0,
            self.tracks(),
            60.0,
            overlap_seconds=2.0,
            word_timestamps=True,
        )
        self.assertEqual(units[2]["extract_start"], 58.0)
        self.assertEqual(units[0]["extract_end"], 62.0)

    def test_default_transcription_is_verbatim_without_context_bias(self):
        self.assertEqual(
            gt.transcription_config(False), {"mode": {"type": "verbatim"}}
        )
        self.assertEqual(gt.no_retry_http_options(), {"retry_options": {"attempts": 0}})
        config = gt.execution_config(
            model="gemini-3.5-transcribe",
            chunk_seconds=900.0,
            overlap_seconds=0.0,
            word_timestamps=False,
            ffmpeg_version="ffmpeg test",
            ffprobe_version="ffprobe test",
            google_genai_version="2.24.0",
        )
        self.assertEqual(config["sdk_retry_attempts"], 0)
        self.assertEqual(config["language_codes"], "auto")
        self.assertIsNone(config["custom_vocabulary"])
        self.assertFalse(config["diarization"])
        self.assertFalse(config["forbidden_context_injected"])

    def test_word_annotation_overlap_assigns_each_word_to_one_core(self):
        units = gt.build_units(
            120.0,
            [{"stream_index": 2, "role": "desktop/source"}],
            60.0,
            overlap_seconds=2.0,
            word_timestamps=True,
        )
        second = units[1]
        words = [
            {"text": "old", "speaker": None, "start_offset": "0.5s", "end_offset": "1.0s"},
            {"text": "new", "speaker": None, "start_offset": "3.0s", "end_offset": "3.5s"},
        ]
        absolute = gt.absolute_word_annotations(words, second)
        self.assertFalse(absolute[0]["owned_by_core"])
        self.assertTrue(absolute[1]["owned_by_core"])
        self.assertEqual(gt.normalized_text("ignored", absolute, overlap_seconds=2.0), "new")

    def test_checkpoint_contains_required_resume_fields_and_next_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = FakeRun(FakeStore(Path(tmp) / "store"))
            unit = gt.build_units(
                60.0, [{"stream_index": 2, "role": "desktop/source"}], 60.0
            )[0]
            interaction = FakeInteraction("hello")
            envelope = gt.response_envelope(
                run=run,
                unit=unit,
                chunk_meta={"sha256": "chunk", "size": 10, "duration": 60.0},
                interaction=interaction,
                file_meta={"name": "files/1", "uri": "uri://1", "mime_type": "audio/flac"},
            )
            checkpoint = gt.make_checkpoint_from_response(
                run=run,
                unit=unit,
                envelope=envelope,
                model="gemini-3.5-transcribe",
                word_timestamps=False,
                overlap_seconds=0.0,
                next_unit_id="next-unit",
            )
            self.assertEqual(checkpoint["track"]["stream_index"], 2)
            self.assertEqual(checkpoint["absolute_start"], 0.0)
            self.assertEqual(checkpoint["input_chunk"]["sha256"], "chunk")
            self.assertEqual(checkpoint["model"], "gemini-3.5-transcribe")
            self.assertEqual(checkpoint["prompt_config_sha256"], "config-hash")
            self.assertEqual(checkpoint["raw_response"]["id"], "interactions/1")
            self.assertEqual(checkpoint["normalized_transcript"], "hello")
            self.assertEqual(checkpoint["validation"]["status"], "VERIFIED")
            self.assertEqual(checkpoint["next_unit"], "next-unit")

    def test_request_intent_is_durable_before_interaction_submit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = FakeRun(FakeStore(root / "store"))
            unit = gt.build_units(
                60.0, [{"stream_index": 2, "role": "desktop/source"}], 60.0
            )[0]
            client = FakeClient(FakeInteraction("spoken text"))
            observed = []

            def create(**_kwargs):
                observed.append(run.state["units"][unit["unit_id"]]["state"])
                return FakeInteraction("spoken text")

            client.interactions.create = create
            chunk_meta = {"sha256": "chunk", "size": 10, "duration": 60.0}
            with patch.object(gt, "extract_chunk", return_value=chunk_meta):
                result = gt.transcribe_one(
                    run=run,
                    workspace=root / "work",
                    source=root / "source.mp4",
                    unit=unit,
                    model="gemini-3.5-transcribe",
                    word_timestamps=False,
                    overlap_seconds=0.0,
                    ffmpeg="ffmpeg",
                    ffprobe="ffprobe",
                    client=client,
                    allow_retry_ambiguous=False,
                    next_unit_id=None,
                )
            self.assertEqual(result, "TRANSCRIBED")
            self.assertEqual(observed, ["REQUEST_INTENT"])

    def test_returned_paid_response_is_saved_before_normalization_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = FakeRun(FakeStore(root / "store"))
            unit = gt.build_units(
                60.0, [{"stream_index": 2, "role": "desktop/source"}], 60.0
            )[0]
            client = FakeClient(FakeInteraction("spoken text", annotations=[]))
            chunk_meta = {"sha256": "chunk", "size": 10, "duration": 60.0}
            with patch.object(gt, "extract_chunk", return_value=chunk_meta):
                with self.assertRaises(gt.TranscriptionError):
                    gt.transcribe_one(
                        run=run,
                        workspace=root / "work",
                        source=root / "source.mp4",
                        unit=unit,
                        model="gemini-3.5-transcribe",
                        word_timestamps=True,
                        overlap_seconds=0.0,
                        ffmpeg="ffmpeg",
                        ffprobe="ffprobe",
                        client=client,
                        allow_retry_ambiguous=False,
                        next_unit_id=None,
                    )
                self.assertEqual(run.state["units"][unit["unit_id"]]["state"], "RESPONSE_SAVED")
                self.assertTrue(gt.local_raw_response(root / "work", unit["unit_id"]).is_file())
                first_calls = client.interactions.calls
                with self.assertRaises(gt.TranscriptionError):
                    gt.transcribe_one(
                        run=run,
                        workspace=root / "work",
                        source=root / "source.mp4",
                        unit=unit,
                        model="gemini-3.5-transcribe",
                        word_timestamps=True,
                        overlap_seconds=0.0,
                        ffmpeg="ffmpeg",
                        ffprobe="ffprobe",
                        client=client,
                        allow_retry_ambiguous=False,
                        next_unit_id=None,
                    )
                self.assertEqual(client.interactions.calls, first_calls)

    def test_ambiguous_paid_request_is_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = FakeRun(FakeStore(root / "store"))
            unit = gt.build_units(
                60.0, [{"stream_index": 2, "role": "desktop/source"}], 60.0
            )[0]
            client = FakeClient(error=RuntimeError("transport broke after submit"))
            chunk_meta = {"sha256": "chunk", "size": 10, "duration": 60.0}
            with patch.object(gt, "extract_chunk", return_value=chunk_meta):
                with self.assertRaises(RuntimeError):
                    gt.transcribe_one(
                        run=run,
                        workspace=root / "work",
                        source=root / "source.mp4",
                        unit=unit,
                        model="gemini-3.5-transcribe",
                        word_timestamps=False,
                        overlap_seconds=0.0,
                        ffmpeg="ffmpeg",
                        ffprobe="ffprobe",
                        client=client,
                        allow_retry_ambiguous=False,
                        next_unit_id=None,
                    )
                self.assertEqual(run.state["units"][unit["unit_id"]]["state"], "AMBIGUOUS")
                first_calls = client.interactions.calls
                with self.assertRaises(gt.TranscriptionError):
                    gt.transcribe_one(
                        run=run,
                        workspace=root / "work",
                        source=root / "source.mp4",
                        unit=unit,
                        model="gemini-3.5-transcribe",
                        word_timestamps=False,
                        overlap_seconds=0.0,
                        ffmpeg="ffmpeg",
                        ffprobe="ffprobe",
                        client=client,
                        allow_retry_ambiguous=False,
                        next_unit_id=None,
                    )
                self.assertEqual(client.interactions.calls, first_calls)

    def test_request_intent_blocks_resume_without_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = FakeRun(FakeStore(root / "store"))
            unit = gt.build_units(
                60.0, [{"stream_index": 2, "role": "desktop/source"}], 60.0
            )[0]
            chunk_meta = {"sha256": "chunk", "size": 10, "duration": 60.0}
            file_meta = {"name": "files/1", "uri": "uri://1", "mime_type": "audio/flac"}
            gt.record_request_intent(run, root / "work", unit, chunk_meta, file_meta)
            client = FakeClient()
            with self.assertRaises(gt.TranscriptionError):
                gt.transcribe_one(
                    run=run,
                    workspace=root / "work",
                    source=root / "source.mp4",
                    unit=unit,
                    model="gemini-3.5-transcribe",
                    word_timestamps=False,
                    overlap_seconds=0.0,
                    ffmpeg="ffmpeg",
                    ffprobe="ffprobe",
                    client=client,
                    allow_retry_ambiguous=False,
                    next_unit_id=None,
                )
            self.assertEqual(client.interactions.calls, 0)

    def test_default_run_id_does_not_silently_fork_when_tool_config_changes(self):
        identity = {
            "sha256": "a" * 64,
            "tracks": self.tracks(),
        }
        first = gt.default_run_id(identity, {"ffmpeg_version": "one"})
        second = gt.default_run_id(identity, {"ffmpeg_version": "two"})
        self.assertEqual(first, second)

    def test_orphan_durable_raw_response_is_recovered_without_new_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FakeStore(root / "store")
            run = FakeRun(store)
            unit = gt.build_units(
                60.0, [{"stream_index": 2, "role": "desktop/source"}], 60.0
            )[0]
            envelope = {
                "schema": gt.RUNNER_SCHEMA,
                "run_id": run.state["run_id"],
                "unit_id": unit["unit_id"],
                "input_chunk": {"sha256": "chunk", "size": 10, "duration": 60.0},
                "uploaded_file": {"name": "files/1", "uri": "uri://1", "mime_type": "audio/flac"},
                "interaction_id": "interactions/orphan",
                "output_text": "already paid",
                "word_annotations": [],
                "raw_response": {"id": "interactions/orphan"},
            }
            raw = root / "raw.json"
            gt.write_json(raw, envelope)
            checksum = gt.material_store.sha256_file(raw)
            store.put(
                raw,
                gt.raw_response_key(run, unit["unit_id"], checksum),
            )
            client = FakeClient()
            result = gt.transcribe_one(
                run=run,
                workspace=root / "work",
                source=root / "source.mp4",
                unit=unit,
                model="gemini-3.5-transcribe",
                word_timestamps=False,
                overlap_seconds=0.0,
                ffmpeg="ffmpeg",
                ffprobe="ffprobe",
                client=client,
                allow_retry_ambiguous=False,
                next_unit_id=None,
            )
            self.assertEqual(result, "NORMALIZED_SAVED_RESPONSE")
            self.assertEqual(client.interactions.calls, 0)
            self.assertEqual(run.state["units"][unit["unit_id"]]["state"], "CHECKPOINTED")

    def test_completion_manifest_requires_every_verified_unit_and_marker_is_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FakeStore(root / "store")
            run = FakeRun(store)
            tracks = self.tracks()
            units = gt.build_units(60.0, tracks, 60.0)
            for index, unit in enumerate(units):
                envelope = {
                    "schema": gt.RUNNER_SCHEMA,
                    "run_id": run.state["run_id"],
                    "unit_id": unit["unit_id"],
                    "input_chunk": {"sha256": f"chunk-{index}"},
                    "uploaded_file": None,
                    "interaction_id": f"i-{index}",
                    "output_text": f"text-{index}",
                    "word_annotations": [],
                    "raw_response": {"id": f"i-{index}"},
                }
                checkpoint = gt.make_checkpoint_from_response(
                    run=run,
                    unit=unit,
                    envelope=envelope,
                    model="gemini-3.5-transcribe",
                    word_timestamps=False,
                    overlap_seconds=0.0,
                    next_unit_id=units[index + 1]["unit_id"] if index + 1 < len(units) else None,
                )
                path = gt.local_verified_checkpoint(root / "work", unit["unit_id"])
                gt.write_json(path, checkpoint)
                gt.attach_checkpoint(run, path, checkpoint)
            manifest = gt.build_completion_manifest(run, units, tracks, 60.0, root / "work")
            self.assertEqual(manifest["validation"]["status"], "PASS")
            self.assertIsNone(gt.find_completion_marker(store, run.state["run_id"]))
            gt.commit_completion(run, root / "work", manifest)
            self.assertIsNotNone(gt.find_completion_marker(store, run.state["run_id"]))
            verified = gt.verify_completion_marker(store, root / "verify", run.state["run_id"])
            self.assertEqual(verified["unit_count"], 2)


if __name__ == "__main__":
    unittest.main()
