"""Crash-resumable clean-room Gemini transcription runner for EP1.

This runner intentionally does one job only: extract the two configured raw
tracks from the current primary recording, transcribe deterministic chunks,
and durably checkpoint verified results. It does not perform source-story
analysis, AV interpretation, scene selection, or editing decisions.

The repository runtime contract remains in ``tools/harness/STATE.json``.
Provider credentials stay outside the repository and are consumed by the
Google Gen AI SDK from the normal environment (for example GEMINI_API_KEY).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import durable_media
import material_store

HERE = Path(__file__).resolve().parent
DEFAULT_STATE = HERE / "STATE.json"
RUNNER_SCHEMA = 1
DEFAULT_MODEL = "gemini-3.5-transcribe"
DEFAULT_CHUNK_SECONDS = 900.0
TRANSCRIPTION_PREFIX = "transcription"
COMPLETION_MARKER = "TRANSCRIPTION_COMPLETED.json"


class TranscriptionError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical(value))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".staging")
    temporary.write_bytes(canonical(value))
    os.replace(temporary, path)


def load_state(path: Path = DEFAULT_STATE) -> dict[str, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    contract = state.get("cleanroom_transcription_run")
    if not isinstance(contract, dict):
        raise TranscriptionError("STATE.json has no cleanroom_transcription_run")
    return state


def ensure_external_workspace(path: Path) -> None:
    repo_root = HERE.parents[1]
    resolved = path.resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        raise TranscriptionError(
            "transcription workspace must stay outside the Git repository"
        )


def command_version(executable: str) -> str:
    proc = subprocess.run(
        [executable, "-version"], text=True, capture_output=True, check=False
    )
    if proc.returncode:
        raise TranscriptionError(f"{executable} -version failed: {proc.stderr.strip()}")
    return (proc.stdout or proc.stderr).splitlines()[0].strip()


def probe_source(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise TranscriptionError(f"ffprobe failed: {proc.stderr.strip()}")
    try:
        probe = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise TranscriptionError("ffprobe returned invalid JSON") from exc
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TranscriptionError("ffprobe did not report source duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise TranscriptionError(f"invalid source duration: {duration!r}")
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise TranscriptionError("ffprobe did not report streams")
    return {"duration": duration, "streams": streams, "raw": probe}


def configured_tracks(state: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = state["cleanroom_transcription_run"].get("input_tracks")
    if not isinstance(tracks, list) or not tracks:
        raise TranscriptionError("cleanroom input_tracks is missing")
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in tracks:
        if not isinstance(item, dict):
            raise TranscriptionError("invalid track contract")
        index = int(item["stream_index"])
        role = str(item["role"])
        if index in seen:
            raise TranscriptionError(f"duplicate configured stream: {index}")
        seen.add(index)
        normalized.append({"stream_index": index, "role": role})
    return normalized


def validate_stream_contract(
    probe: dict[str, Any], tracks: list[dict[str, Any]]
) -> None:
    by_index = {
        int(stream["index"]): stream
        for stream in probe["streams"]
        if "index" in stream
    }
    for track in tracks:
        index = track["stream_index"]
        stream = by_index.get(index)
        if not stream:
            raise TranscriptionError(f"configured stream {index} is missing")
        if stream.get("codec_type") != "audio":
            raise TranscriptionError(f"configured stream {index} is not audio")
    if any(track["stream_index"] == 1 for track in tracks):
        raise TranscriptionError("mixed audio stream 1 is forbidden")


def verify_primary_source(
    state: dict[str, Any], state_path: Path, local_path: Path | None
) -> tuple[Path, dict[str, Any]]:
    artifact_id = str(state["cleanroom_transcription_run"]["source_artifact"])
    record = material_store.artifact_record(artifact_id, state_path)
    source = (
        local_path.expanduser()
        if local_path is not None
        else material_store.local_path_for_key(str(record["object_key"]))
    )
    problems = material_store.verify_path(source, record)
    if problems:
        raise TranscriptionError("primary source verification failed: " + "; ".join(problems))
    return source, record


def unit_id(stream_index: int, segment_index: int, start: float, end: float) -> str:
    start_ms = int(round(start * 1000.0))
    end_ms = int(round(end * 1000.0))
    return f"s{stream_index:02d}_c{segment_index:04d}_{start_ms:010d}_{end_ms:010d}"


def build_units(
    duration: float,
    tracks: list[dict[str, Any]],
    chunk_seconds: float,
    overlap_seconds: float = 0.0,
    *,
    word_timestamps: bool = False,
) -> list[dict[str, Any]]:
    if chunk_seconds <= 0:
        raise TranscriptionError("chunk_seconds must be positive")
    if overlap_seconds < 0:
        raise TranscriptionError("overlap_seconds must be non-negative")
    if overlap_seconds >= chunk_seconds / 2:
        raise TranscriptionError("overlap_seconds must be less than half chunk_seconds")
    if overlap_seconds and not word_timestamps:
        raise TranscriptionError(
            "overlap requires word timestamps so duplicate ownership is deterministic"
        )

    segment_count = int(math.ceil(duration / chunk_seconds))
    units: list[dict[str, Any]] = []
    for segment_index in range(segment_count):
        core_start = segment_index * chunk_seconds
        core_end = min(duration, (segment_index + 1) * chunk_seconds)
        extract_start = max(0.0, core_start - (overlap_seconds if segment_index else 0.0))
        extract_end = min(
            duration,
            core_end + (overlap_seconds if segment_index < segment_count - 1 else 0.0),
        )
        for track in tracks:
            units.append(
                {
                    "unit_id": unit_id(
                        track["stream_index"], segment_index, core_start, core_end
                    ),
                    "segment_index": segment_index,
                    "stream_index": track["stream_index"],
                    "role": track["role"],
                    "core_start": round(core_start, 6),
                    "core_end": round(core_end, 6),
                    "extract_start": round(extract_start, 6),
                    "extract_end": round(extract_end, 6),
                }
            )
    return units


def transcription_config(word_timestamps: bool) -> dict[str, Any]:
    mode: dict[str, Any] = {"type": "verbatim"}
    if word_timestamps:
        mode["timestamp_granularities"] = ["word"]
    return {"mode": mode}


def no_retry_http_options() -> dict[str, Any]:
    """Disable SDK retries so one application submit means one provider submit."""
    return {"retry_options": {"attempts": 0}}


def execution_config(
    *,
    model: str,
    chunk_seconds: float,
    overlap_seconds: float,
    word_timestamps: bool,
    ffmpeg_version: str,
    ffprobe_version: str,
    google_genai_version: str,
) -> dict[str, Any]:
    return {
        "runner_schema": RUNNER_SCHEMA,
        "model": model,
        "api": "Gemini Interactions API + Files API",
        "transcription_config": transcription_config(word_timestamps),
        "sdk_retry_attempts": 0,
        "language_codes": "auto",
        "custom_vocabulary": None,
        "diarization": False,
        "chunk_seconds": chunk_seconds,
        "overlap_seconds": overlap_seconds,
        "audio_container": "flac",
        "preserve_track_channels": True,
        "ffmpeg_version": ffmpeg_version,
        "ffprobe_version": ffprobe_version,
        "google_genai_version": google_genai_version,
        "python_version": sys.version.split()[0],
        "forbidden_context_injected": False,
    }


def source_identity(
    *,
    artifact_id: str,
    record: dict[str, Any],
    duration: float,
    tracks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "object_key": record["object_key"],
        "size": int(record["size"]),
        "sha256": str(record["sha256"]),
        "duration": round(duration, 6),
        "tracks": tracks,
    }


def default_run_id(identity: dict[str, Any], config: dict[str, Any]) -> str:
    track_hash = sha256_json(identity.get("tracks", []))[:8]
    return (
        f"gemini-transcribe-{str(identity['sha256'])[:12]}-"
        f"{track_hash}-v{RUNNER_SCHEMA}"
    )


def ffmpeg_timestamp(value: float) -> str:
    return f"{value:.6f}"


def extract_chunk(
    source: Path,
    unit: dict[str, Any],
    target: Path,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.stem + ".partial" + target.suffix)
    staging.unlink(missing_ok=True)
    duration = float(unit["extract_end"]) - float(unit["extract_start"])
    command = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-ss",
        ffmpeg_timestamp(float(unit["extract_start"])),
        "-t",
        ffmpeg_timestamp(duration),
        "-map",
        f"0:{int(unit['stream_index'])}",
        "-vn",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-c:a",
        "flac",
        str(staging),
    ]
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if proc.returncode:
        staging.unlink(missing_ok=True)
        raise TranscriptionError(
            f"ffmpeg extraction failed for {unit['unit_id']}: {proc.stderr.strip()}"
        )
    os.replace(staging, target)

    probe = probe_source(target, ffprobe=ffprobe)
    audio_streams = [
        stream for stream in probe["streams"] if stream.get("codec_type") == "audio"
    ]
    if len(audio_streams) != 1:
        target.unlink(missing_ok=True)
        raise TranscriptionError(
            f"extracted chunk has {len(audio_streams)} audio streams: {unit['unit_id']}"
        )
    expected = duration
    actual = float(probe["duration"])
    if abs(actual - expected) > 0.75:
        target.unlink(missing_ok=True)
        raise TranscriptionError(
            f"chunk duration mismatch {unit['unit_id']}: expected={expected:.3f} actual={actual:.3f}"
        )
    return {
        "path": str(target),
        "size": target.stat().st_size,
        "sha256": material_store.sha256_file(target),
        "duration": round(actual, 6),
        "mime_type": "audio/flac",
    }


def interaction_to_json(interaction: Any) -> Any:
    model_dump = getattr(interaction, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json", by_alias=True, exclude_none=False)
        except TypeError:
            return model_dump()
    to_json_dict = getattr(interaction, "to_json_dict", None)
    if callable(to_json_dict):
        return to_json_dict()
    if isinstance(interaction, (dict, list, str, int, float, bool)) or interaction is None:
        return interaction
    if hasattr(interaction, "__dict__"):
        return {
            key: interaction_to_json(value)
            for key, value in vars(interaction).items()
            if not key.startswith("_")
        }
    return repr(interaction)


def extract_word_annotations(interaction: Any) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for step in getattr(interaction, "steps", []) or []:
        for content in getattr(step, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", None) != "word_info":
                    continue
                words.append(
                    {
                        "text": str(getattr(annotation, "text", "")),
                        "speaker": getattr(annotation, "speaker", None),
                        "start_offset": str(getattr(annotation, "start_offset", "")),
                        "end_offset": str(getattr(annotation, "end_offset", "")),
                    }
                )
    return words


def parse_offset_seconds(raw: str) -> float:
    value = raw.strip()
    if value.endswith("s"):
        value = value[:-1]
    try:
        seconds = float(value)
    except ValueError as exc:
        raise TranscriptionError(f"invalid word offset: {raw!r}") from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise TranscriptionError(f"invalid word offset: {raw!r}")
    return seconds


def absolute_word_annotations(
    words: list[dict[str, Any]], unit: dict[str, Any]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous = -1.0
    extract_start = float(unit["extract_start"])
    extract_end = float(unit["extract_end"])
    core_start = float(unit["core_start"])
    core_end = float(unit["core_end"])
    for word in words:
        start = extract_start + parse_offset_seconds(word["start_offset"])
        end = extract_start + parse_offset_seconds(word["end_offset"])
        if end < start or start + 1e-6 < previous:
            raise TranscriptionError(
                f"non-monotonic word annotations: {unit['unit_id']}"
            )
        if start < extract_start - 0.5 or end > extract_end + 0.5:
            raise TranscriptionError(
                f"word annotation outside extracted chunk: {unit['unit_id']}"
            )
        previous = start
        midpoint = (start + end) / 2.0
        owned = core_start <= midpoint < core_end or (
            math.isclose(midpoint, core_end, abs_tol=1e-6)
            and math.isclose(core_end, extract_end, abs_tol=1e-6)
        )
        output.append(
            {
                **word,
                "absolute_start": round(start, 6),
                "absolute_end": round(end, 6),
                "owned_by_core": owned,
            }
        )
    return output


def normalized_text(
    output_text: str,
    annotations: list[dict[str, Any]],
    *,
    overlap_seconds: float,
) -> str:
    if not overlap_seconds:
        return output_text
    owned = [word["text"] for word in annotations if word.get("owned_by_core")]
    return " ".join(text for text in owned if text).strip()


def new_genai_client() -> Any:
    try:
        from google import genai  # type: ignore
    except ImportError as exc:
        raise TranscriptionError(
            "google-genai is required; install tools/harness/requirements_gemini.txt"
        ) from exc
    return genai.Client(http_options=no_retry_http_options())


def best_effort_delete_file(client: Any, file_meta: dict[str, Any]) -> str | None:
    name = file_meta.get("name")
    if not name:
        return None
    try:
        client.files.delete(name=name)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def local_raw_response(workspace: Path, unit_id_value: str) -> Path:
    return workspace / "raw_responses" / f"{unit_id_value}.json"


def raw_response_key(run: durable_media.Run, unit_id_value: str, sha256: str) -> str:
    return (
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/raw_responses/"
        f"{unit_id_value}/{sha256}.json"
    )


def response_envelope(
    *,
    run: durable_media.Run,
    unit: dict[str, Any],
    chunk_meta: dict[str, Any],
    interaction: Any,
    file_meta: dict[str, Any],
) -> dict[str, Any]:
    output_text = getattr(interaction, "output_text", None)
    if output_text is None:
        raise TranscriptionError("Gemini interaction returned no output_text")
    return {
        "schema": RUNNER_SCHEMA,
        "run_id": run.state["run_id"],
        "unit_id": unit["unit_id"],
        "input_chunk": chunk_meta,
        "uploaded_file": file_meta,
        "interaction_id": str(getattr(interaction, "id", "")),
        "output_text": str(output_text),
        "word_annotations": extract_word_annotations(interaction),
        "raw_response": interaction_to_json(interaction),
        "received_at": time.time(),
    }


def validate_response_envelope(
    envelope: dict[str, Any], run: durable_media.Run, unit: dict[str, Any]
) -> None:
    if envelope.get("schema") != RUNNER_SCHEMA:
        raise TranscriptionError(f"raw response schema mismatch: {unit['unit_id']}")
    if envelope.get("run_id") != run.state["run_id"]:
        raise TranscriptionError(f"raw response run mismatch: {unit['unit_id']}")
    if envelope.get("unit_id") != unit["unit_id"]:
        raise TranscriptionError(f"raw response unit mismatch: {unit['unit_id']}")
    if not isinstance(envelope.get("output_text"), str):
        raise TranscriptionError(f"raw response has no output text: {unit['unit_id']}")
    chunk = envelope.get("input_chunk")
    if not isinstance(chunk, dict) or not chunk.get("sha256"):
        raise TranscriptionError(f"raw response has no chunk identity: {unit['unit_id']}")


def attach_raw_response(
    run: durable_media.Run,
    response_path: Path,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    unit = str(envelope["unit_id"])
    checksum = material_store.sha256_file(response_path)
    receipt = run.store.put(response_path, raw_response_key(run, unit, checksum))
    durable_media.verify(response_path, receipt)
    run.state["units"][unit] = {
        "state": "RESPONSE_SAVED",
        "receipt": receipt,
        "input_identity": run.state["input_identity"],
        "config_sha256": run.state["config_sha256"],
        "input_chunk_sha256": envelope["input_chunk"]["sha256"],
        "interaction_id": envelope.get("interaction_id", ""),
    }
    run.save()
    return receipt


def restore_raw_response(
    run: durable_media.Run, unit: dict[str, Any], target: Path
) -> dict[str, Any] | None:
    entry = run.state.get("units", {}).get(unit["unit_id"])
    if not entry or entry.get("state") != "RESPONSE_SAVED":
        return None
    if entry.get("input_identity") != run.state["input_identity"]:
        raise TranscriptionError(f"raw response input mismatch: {unit['unit_id']}")
    if entry.get("config_sha256") != run.state["config_sha256"]:
        raise TranscriptionError(f"raw response config mismatch: {unit['unit_id']}")
    run.store.get(entry["receipt"], target)
    envelope = json.loads(target.read_text(encoding="utf-8"))
    validate_response_envelope(envelope, run, unit)
    return envelope


def recover_orphan_raw_response(
    run: durable_media.Run,
    workspace: Path,
    unit: dict[str, Any],
) -> tuple[dict[str, Any], Path] | None:
    prefix = (
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/raw_responses/"
        f"{unit['unit_id']}"
    )
    candidates = []
    for index, key in enumerate(run.store.keys(prefix)):
        name = key.rsplit("/", 1)[-1]
        checksum = name[:-5] if name.endswith(".json") else ""
        if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            continue
        target = workspace / "orphan_raw" / f"{unit['unit_id']}_{index}.json"
        run.store.get({"key": key, "size": None, "sha256": checksum}, target)
        envelope = json.loads(target.read_text(encoding="utf-8"))
        validate_response_envelope(envelope, run, unit)
        candidates.append((envelope, target))
    if not candidates:
        return None
    if len(candidates) > 1:
        raise TranscriptionError(
            f"multiple unjournaled raw responses require audit: {unit['unit_id']}"
        )
    envelope, target = candidates[0]
    attach_raw_response(run, target, envelope)
    return envelope, target


def checkpoint_key(run: durable_media.Run, unit_id_value: str, sha256: str) -> str:
    return (
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/checkpoints/"
        f"{unit_id_value}/{sha256}.json"
    )


def attach_checkpoint(
    run: durable_media.Run,
    checkpoint_path: Path,
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    unit = str(checkpoint["unit_id"])
    checksum = material_store.sha256_file(checkpoint_path)
    receipt = run.store.put(checkpoint_path, checkpoint_key(run, unit, checksum))
    durable_media.verify(checkpoint_path, receipt)
    run.state["units"][unit] = {
        "state": "CHECKPOINTED",
        "receipt": receipt,
        "input_identity": run.state["input_identity"],
        "config_sha256": run.state["config_sha256"],
        "track": {
            "stream_index": checkpoint["track"]["stream_index"],
            "role": checkpoint["track"]["role"],
        },
        "absolute_start": checkpoint["absolute_start"],
        "absolute_end": checkpoint["absolute_end"],
        "input_chunk_sha256": checkpoint["input_chunk"]["sha256"],
        "model": checkpoint["model"],
        "prompt_config_sha256": checkpoint["prompt_config_sha256"],
        "validation": checkpoint["validation"],
    }
    run.save()
    return receipt


def restore_checkpoint(
    run: durable_media.Run, unit: dict[str, Any], target: Path
) -> dict[str, Any] | None:
    entry = run.state.get("units", {}).get(unit["unit_id"])
    if not entry or entry.get("state") != "CHECKPOINTED":
        return None
    if entry.get("input_identity") != run.state["input_identity"]:
        raise TranscriptionError(f"checkpoint input mismatch: {unit['unit_id']}")
    if entry.get("config_sha256") != run.state["config_sha256"]:
        raise TranscriptionError(f"checkpoint config mismatch: {unit['unit_id']}")
    run.store.get(entry["receipt"], target)
    checkpoint = json.loads(target.read_text(encoding="utf-8"))
    validate_checkpoint(checkpoint, run, unit)
    return checkpoint


def validate_checkpoint(
    checkpoint: dict[str, Any], run: durable_media.Run, unit: dict[str, Any]
) -> None:
    if checkpoint.get("schema") != RUNNER_SCHEMA:
        raise TranscriptionError(f"checkpoint schema mismatch: {unit['unit_id']}")
    if checkpoint.get("run_id") != run.state["run_id"]:
        raise TranscriptionError(f"checkpoint run mismatch: {unit['unit_id']}")
    if checkpoint.get("unit_id") != unit["unit_id"]:
        raise TranscriptionError(f"checkpoint unit mismatch: {unit['unit_id']}")
    if checkpoint.get("validation", {}).get("status") != "VERIFIED":
        raise TranscriptionError(f"checkpoint is not verified: {unit['unit_id']}")
    if checkpoint.get("prompt_config_sha256") != run.state["config_sha256"]:
        raise TranscriptionError(f"checkpoint config hash mismatch: {unit['unit_id']}")
    for field in ("core_start", "core_end", "extract_start", "extract_end"):
        expected = float(unit[field])
        actual = float(checkpoint["timing"][field])
        if not math.isclose(expected, actual, abs_tol=1e-6):
            raise TranscriptionError(
                f"checkpoint timing mismatch {unit['unit_id']} {field}"
            )


def local_verified_checkpoint(workspace: Path, unit_id_value: str) -> Path:
    return workspace / "verified" / f"{unit_id_value}.json"


def ambiguous_checkpoint(workspace: Path, unit_id_value: str) -> Path:
    return workspace / "ambiguous" / f"{unit_id_value}.json"


def request_intent_checkpoint(workspace: Path, unit_id_value: str) -> Path:
    return workspace / "request_intent" / f"{unit_id_value}.json"


def record_request_intent(
    run: durable_media.Run,
    workspace: Path,
    unit: dict[str, Any],
    chunk_meta: dict[str, Any],
    file_meta: dict[str, Any],
) -> None:
    record = {
        "schema": RUNNER_SCHEMA,
        "run_id": run.state["run_id"],
        "unit_id": unit["unit_id"],
        "state": "REQUEST_INTENT",
        "reason": (
            "Durable intent recorded before the paid Interactions API submit. "
            "If the process disappears before a durable response exists, automatic retry is blocked."
        ),
        "track": {
            "stream_index": unit["stream_index"],
            "role": unit["role"],
        },
        "timing": unit,
        "input_chunk": chunk_meta,
        "uploaded_file": file_meta,
        "recorded_at": time.time(),
    }
    path = request_intent_checkpoint(workspace, unit["unit_id"])
    write_json(path, record)
    checksum = material_store.sha256_file(path)
    receipt = run.store.put(
        path,
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/request_intent/{unit['unit_id']}/{checksum}.json",
    )
    durable_media.verify(path, receipt)
    run.state["units"][unit["unit_id"]] = {
        "state": "REQUEST_INTENT",
        "receipt": receipt,
        "input_identity": run.state["input_identity"],
        "config_sha256": run.state["config_sha256"],
        "input_chunk_sha256": chunk_meta["sha256"],
    }
    run.save()


def record_ambiguous(
    run: durable_media.Run,
    workspace: Path,
    unit: dict[str, Any],
    chunk_meta: dict[str, Any],
    file_meta: dict[str, Any] | None,
    exc: BaseException,
) -> None:
    record = {
        "schema": RUNNER_SCHEMA,
        "run_id": run.state["run_id"],
        "unit_id": unit["unit_id"],
        "state": "AMBIGUOUS",
        "reason": (
            "A paid transcription request may have been accepted but no verified "
            "response checkpoint exists. Automatic retry is blocked to avoid double billing."
        ),
        "track": {
            "stream_index": unit["stream_index"],
            "role": unit["role"],
        },
        "timing": unit,
        "input_chunk": chunk_meta,
        "uploaded_file": file_meta,
        "error": {"type": type(exc).__name__, "message": str(exc)},
        "recorded_at": time.time(),
    }
    path = ambiguous_checkpoint(workspace, unit["unit_id"])
    write_json(path, record)
    checksum = material_store.sha256_file(path)
    receipt = run.store.put(
        path,
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/ambiguous/{unit['unit_id']}/{checksum}.json",
    )
    durable_media.verify(path, receipt)
    run.state["units"][unit["unit_id"]] = {
        "state": "AMBIGUOUS",
        "receipt": receipt,
        "input_identity": run.state["input_identity"],
        "config_sha256": run.state["config_sha256"],
    }
    run.save()


def make_checkpoint_from_response(
    *,
    run: durable_media.Run,
    unit: dict[str, Any],
    envelope: dict[str, Any],
    model: str,
    word_timestamps: bool,
    overlap_seconds: float,
    next_unit_id: str | None,
) -> dict[str, Any]:
    validate_response_envelope(envelope, run, unit)
    output_text = envelope["output_text"]
    raw_words = envelope.get("word_annotations", []) if word_timestamps else []
    absolute_words = (
        absolute_word_annotations(raw_words, unit) if word_timestamps else []
    )
    if word_timestamps and output_text.strip() and not absolute_words:
        raise TranscriptionError(
            f"word timestamps were requested but none were returned: {unit['unit_id']}"
        )
    normalized = normalized_text(
        output_text, absolute_words, overlap_seconds=overlap_seconds
    )
    return {
        "schema": RUNNER_SCHEMA,
        "run_id": run.state["run_id"],
        "unit_id": unit["unit_id"],
        "track": {
            "stream_index": unit["stream_index"],
            "role": unit["role"],
        },
        "absolute_start": unit["core_start"],
        "absolute_end": unit["core_end"],
        "timing": {
            "core_start": unit["core_start"],
            "core_end": unit["core_end"],
            "extract_start": unit["extract_start"],
            "extract_end": unit["extract_end"],
        },
        "input_chunk": envelope["input_chunk"],
        "model": model,
        "transcription_config": transcription_config(word_timestamps),
        "prompt_config_sha256": run.state["config_sha256"],
        "uploaded_file": envelope.get("uploaded_file"),
        "interaction_id": envelope.get("interaction_id", ""),
        "raw_response": envelope.get("raw_response"),
        "output_text": output_text,
        "normalized_transcript": normalized,
        "word_annotations": absolute_words,
        "validation": {
            "status": "VERIFIED",
            "raw_response_durable_before_normalization": True,
            "word_annotations_checked": bool(word_timestamps),
        },
        "verified_at": time.time(),
        "next_unit": next_unit_id,
    }


def validate_plan_coverage(
    units: list[dict[str, Any]], tracks: list[dict[str, Any]], duration: float
) -> dict[str, Any]:
    result: dict[str, Any] = {"tracks": {}}
    for track in tracks:
        index = track["stream_index"]
        ordered = sorted(
            (unit for unit in units if unit["stream_index"] == index),
            key=lambda unit: (unit["core_start"], unit["core_end"]),
        )
        if not ordered:
            raise TranscriptionError(f"no units for stream {index}")
        if not math.isclose(float(ordered[0]["core_start"]), 0.0, abs_tol=1e-6):
            raise TranscriptionError(f"stream {index} does not start at zero")
        previous_end = 0.0
        for unit in ordered:
            start = float(unit["core_start"])
            end = float(unit["core_end"])
            if not math.isclose(start, previous_end, abs_tol=1e-6):
                raise TranscriptionError(
                    f"stream {index} has gap/duplicate core coverage at {start}"
                )
            if end <= start:
                raise TranscriptionError(f"invalid unit interval: {unit['unit_id']}")
            previous_end = end
        if not math.isclose(previous_end, duration, abs_tol=1e-5):
            raise TranscriptionError(
                f"stream {index} final coverage {previous_end} != {duration}"
            )
        result["tracks"][str(index)] = {
            "role": track["role"],
            "unit_count": len(ordered),
            "start": 0.0,
            "end": round(previous_end, 6),
            "gaps": 0,
            "core_duplicates": 0,
            "order": "PASS",
        }
    result["status"] = "PASS"
    return result


def build_completion_manifest(
    run: durable_media.Run,
    units: list[dict[str, Any]],
    tracks: list[dict[str, Any]],
    duration: float,
    workspace: Path,
) -> dict[str, Any]:
    coverage = validate_plan_coverage(units, tracks, duration)
    checkpoint_summaries: list[dict[str, Any]] = []
    duplicate_word_keys: set[tuple[Any, ...]] = set()
    duplicate_words: list[tuple[Any, ...]] = []
    for unit in units:
        target = workspace / "completion_checkpoints" / f"{unit['unit_id']}.json"
        checkpoint = restore_checkpoint(run, unit, target)
        if checkpoint is None:
            raise TranscriptionError(f"missing verified checkpoint: {unit['unit_id']}")
        for word in checkpoint.get("word_annotations", []):
            if not word.get("owned_by_core"):
                continue
            key = (
                unit["stream_index"],
                word.get("text"),
                word.get("absolute_start"),
                word.get("absolute_end"),
            )
            if key in duplicate_word_keys:
                duplicate_words.append(key)
            duplicate_word_keys.add(key)
        checkpoint_summaries.append(
            {
                "unit_id": unit["unit_id"],
                "track": checkpoint["track"],
                "absolute_start": checkpoint["absolute_start"],
                "absolute_end": checkpoint["absolute_end"],
                "input_chunk_sha256": checkpoint["input_chunk"]["sha256"],
                "model": checkpoint["model"],
                "prompt_config_sha256": checkpoint["prompt_config_sha256"],
                "normalized_transcript": checkpoint["normalized_transcript"],
                "receipt": run.state["units"][unit["unit_id"]]["receipt"],
            }
        )
    if duplicate_words:
        raise TranscriptionError(
            f"duplicate owned word annotations detected: {len(duplicate_words)}"
        )
    return {
        "schema": RUNNER_SCHEMA,
        "kind": "cleanroom_gemini_retranscription",
        "run_id": run.state["run_id"],
        "input_identity": run.state["input_identity"],
        "config_sha256": run.state["config_sha256"],
        "coverage": coverage,
        "unit_count": len(units),
        "units": checkpoint_summaries,
        "validation": {
            "status": "PASS",
            "all_units_verified": True,
            "gap_check": "PASS",
            "duplicate_core_check": "PASS",
            "order_check": "PASS",
            "duplicate_owned_word_check": "PASS",
        },
        "stop_after": "retranscription completion validation",
        "completed_at": time.time(),
    }


def completion_marker_key(run_id: str) -> str:
    return f"runs/{run_id}/{COMPLETION_MARKER}"


def find_completion_marker(store: Any, run_id: str) -> str | None:
    expected = completion_marker_key(run_id)
    for key in store.keys(f"runs/{run_id}"):
        if key == expected:
            return key
    return None


def verify_completion_marker(
    store: Any, workspace: Path, run_id: str
) -> dict[str, Any] | None:
    key = find_completion_marker(store, run_id)
    if key is None:
        return None
    marker_path = workspace / "completion_marker.json"
    store.get({"key": key, "size": None, "sha256": None}, marker_path)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("schema") != RUNNER_SCHEMA or marker.get("run_id") != run_id:
        raise TranscriptionError("invalid transcription completion marker")
    manifest_receipt = marker.get("manifest")
    if not isinstance(manifest_receipt, dict):
        raise TranscriptionError("completion marker has no manifest receipt")
    manifest_path = workspace / "completion_manifest.json"
    store.get(manifest_receipt, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("run_id") != run_id
        or manifest.get("validation", {}).get("status") != "PASS"
    ):
        raise TranscriptionError("invalid transcription completion manifest")
    return manifest


def commit_completion(
    run: durable_media.Run, workspace: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    existing = verify_completion_marker(run.store, workspace / "existing", run.state["run_id"])
    if existing is not None:
        return existing
    manifest_path = workspace / "final" / "manifest.json"
    write_json(manifest_path, manifest)
    manifest_hash = material_store.sha256_file(manifest_path)
    manifest_receipt = run.store.put(
        manifest_path,
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/manifests/{manifest_hash}.json",
    )
    durable_media.verify(manifest_path, manifest_receipt)
    run.state.update(
        {
            "state": "TRANSCRIPTION_VALIDATED",
            "transcription_manifest": manifest_receipt,
        }
    )
    run.save()

    marker = {
        "schema": RUNNER_SCHEMA,
        "kind": "cleanroom_gemini_retranscription",
        "run_id": run.state["run_id"],
        "manifest": manifest_receipt,
        "input_identity": run.state["input_identity"],
        "config_sha256": run.state["config_sha256"],
        "created_at": time.time(),
    }
    marker_path = workspace / "final" / COMPLETION_MARKER
    write_json(marker_path, marker)
    marker_receipt = run.store.put(marker_path, completion_marker_key(run.state["run_id"]))
    durable_media.verify(marker_path, marker_receipt)
    return manifest


def durable_run_plan(
    run: durable_media.Run,
    workspace: Path,
    units: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    if run.state.get("transcription_plan"):
        return
    plan = {
        "schema": RUNNER_SCHEMA,
        "kind": "cleanroom_gemini_retranscription_plan",
        "run_id": run.state["run_id"],
        "input_identity": run.state["input_identity"],
        "config": config,
        "config_sha256": run.state["config_sha256"],
        "unit_count": len(units),
        "units": units,
        "created_at": time.time(),
    }
    path = workspace / "run_plan.json"
    write_json(path, plan)
    checksum = material_store.sha256_file(path)
    receipt = run.store.put(
        path,
        f"{run.prefix}/{TRANSCRIPTION_PREFIX}/plans/{checksum}.json",
    )
    run.state["transcription_plan"] = receipt
    run.save()


def pause_run(run: durable_media.Run) -> None:
    run.state["state"] = "PAUSED"
    run.state["lease"]["seconds"] = 0.0
    run.save()


def open_or_create_run(
    store: Any,
    workspace: Path,
    identity: dict[str, Any],
    config: dict[str, Any],
    run_id: str,
    *,
    lease_seconds: float,
    takeover: bool,
) -> durable_media.Run:
    if store.keys(f"runs/{run_id}"):
        latest = durable_media.read_journal(store, workspace / "open_check", run_id)
        paused = latest.get("state") == "PAUSED"
        run = durable_media.recover(
            store, workspace, run_id, takeover=(takeover or paused)
        )
        if not run.holder:
            raise TranscriptionError(
                "run has an active lease; use the existing process or wait for lease expiry"
            )
        if run.state.get("input_identity") != identity:
            raise TranscriptionError("existing run input identity does not match")
        expected_config = sha256_json(config)
        if run.state.get("config_sha256") != expected_config:
            raise TranscriptionError("existing run config does not match")
        run.state["state"] = "RUNNING"
        run.state["lease"]["seconds"] = lease_seconds
        run.save()
        return run
    return durable_media.create(
        store,
        workspace,
        identity,
        config,
        run_id,
        lease_seconds=lease_seconds,
    )


def transcribe_one(
    *,
    run: durable_media.Run,
    workspace: Path,
    source: Path,
    unit: dict[str, Any],
    model: str,
    word_timestamps: bool,
    overlap_seconds: float,
    ffmpeg: str,
    ffprobe: str,
    client: Any,
    allow_retry_ambiguous: bool,
    next_unit_id: str | None,
) -> str:
    recovered_path = workspace / "recovered_checkpoints" / f"{unit['unit_id']}.json"
    if restore_checkpoint(run, unit, recovered_path) is not None:
        return "REUSED"

    local_verified = local_verified_checkpoint(workspace, unit["unit_id"])
    if local_verified.is_file():
        checkpoint = json.loads(local_verified.read_text(encoding="utf-8"))
        validate_checkpoint(checkpoint, run, unit)
        attach_checkpoint(run, local_verified, checkpoint)
        return "REPUBLISHED"

    raw_path = local_raw_response(workspace, unit["unit_id"])
    envelope: dict[str, Any] | None = None
    if raw_path.is_file():
        envelope = json.loads(raw_path.read_text(encoding="utf-8"))
        validate_response_envelope(envelope, run, unit)
        attach_raw_response(run, raw_path, envelope)
    else:
        restored_raw = workspace / "recovered_raw" / f"{unit['unit_id']}.json"
        envelope = restore_raw_response(run, unit, restored_raw)
        if envelope is not None:
            raw_path = restored_raw

    if envelope is None:
        orphan = recover_orphan_raw_response(run, workspace, unit)
        if orphan is not None:
            envelope, raw_path = orphan

    if envelope is not None:
        checkpoint = make_checkpoint_from_response(
            run=run,
            unit=unit,
            envelope=envelope,
            model=model,
            word_timestamps=word_timestamps,
            overlap_seconds=overlap_seconds,
            next_unit_id=next_unit_id,
        )
        write_json(local_verified, checkpoint)
        attach_checkpoint(run, local_verified, checkpoint)
        return "NORMALIZED_SAVED_RESPONSE"

    existing_entry = run.state.get("units", {}).get(unit["unit_id"])
    local_ambiguous = ambiguous_checkpoint(workspace, unit["unit_id"])
    local_intent = request_intent_checkpoint(workspace, unit["unit_id"])
    unresolved_state = existing_entry and existing_entry.get("state") in {
        "AMBIGUOUS",
        "REQUEST_INTENT",
    }
    unresolved = bool(unresolved_state) or local_ambiguous.is_file() or local_intent.is_file()
    if unresolved and not allow_retry_ambiguous:
        raise TranscriptionError(
            f"unresolved paid request blocked from automatic retry: {unit['unit_id']}"
        )
    if unresolved and allow_retry_ambiguous:
        run.state.get("units", {}).pop(unit["unit_id"], None)
        local_ambiguous.unlink(missing_ok=True)
        local_intent.unlink(missing_ok=True)
        run.save()

    chunk = workspace / "chunks" / f"{unit['unit_id']}.flac"
    chunk_meta = extract_chunk(
        source, unit, chunk, ffmpeg=ffmpeg, ffprobe=ffprobe
    )
    file_meta: dict[str, Any] | None = None
    interaction_started = False
    response_durable = False
    try:
        uploaded = client.files.upload(file=str(chunk))
        file_meta = {
            "name": str(getattr(uploaded, "name", "")),
            "uri": str(getattr(uploaded, "uri", "")),
            "mime_type": str(
                getattr(uploaded, "mime_type", "audio/flac") or "audio/flac"
            ),
        }
        if not file_meta["uri"]:
            raise TranscriptionError("Gemini Files API returned no file URI")
        record_request_intent(run, workspace, unit, chunk_meta, file_meta)
        interaction_started = True
        interaction = client.interactions.create(
            model=model,
            input=[
                {
                    "type": "audio",
                    "uri": file_meta["uri"],
                    "mime_type": file_meta["mime_type"],
                }
            ],
            generation_config={
                "transcription_config": transcription_config(word_timestamps)
            },
        )
        envelope = response_envelope(
            run=run,
            unit=unit,
            chunk_meta=chunk_meta,
            interaction=interaction,
            file_meta=file_meta,
        )
        write_json(raw_path, envelope)
        attach_raw_response(run, raw_path, envelope)
        response_durable = True
        checkpoint = make_checkpoint_from_response(
            run=run,
            unit=unit,
            envelope=envelope,
            model=model,
            word_timestamps=word_timestamps,
            overlap_seconds=overlap_seconds,
            next_unit_id=next_unit_id,
        )
        write_json(local_verified, checkpoint)
        attach_checkpoint(run, local_verified, checkpoint)
    except BaseException as exc:
        if interaction_started and not response_durable:
            record_ambiguous(run, workspace, unit, chunk_meta, file_meta, exc)
        raise
    finally:
        if file_meta:
            cleanup_error = best_effort_delete_file(client, file_meta)
            if cleanup_error:
                print(
                    f"WARN file cleanup failed for {unit['unit_id']}: {cleanup_error}",
                    file=sys.stderr,
                )
    return "TRANSCRIBED"


def installed_google_genai_version() -> str:
    try:
        return importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def build_context(args: argparse.Namespace) -> dict[str, Any]:
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    source, record = verify_primary_source(
        state,
        state_path,
        Path(args.source).resolve() if args.source else None,
    )
    probe = probe_source(source, ffprobe=args.ffprobe)
    tracks = configured_tracks(state)
    validate_stream_contract(probe, tracks)
    units = build_units(
        probe["duration"],
        tracks,
        args.chunk_seconds,
        args.overlap_seconds,
        word_timestamps=args.word_timestamps,
    )
    coverage = validate_plan_coverage(units, tracks, probe["duration"])
    config = execution_config(
        model=args.model,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
        word_timestamps=args.word_timestamps,
        ffmpeg_version=command_version(args.ffmpeg),
        ffprobe_version=command_version(args.ffprobe),
        google_genai_version=installed_google_genai_version(),
    )
    artifact_id = str(state["cleanroom_transcription_run"]["source_artifact"])
    identity = source_identity(
        artifact_id=artifact_id,
        record=record,
        duration=probe["duration"],
        tracks=tracks,
    )
    return {
        "state": state,
        "state_path": state_path,
        "source": source,
        "record": record,
        "probe": probe,
        "tracks": tracks,
        "units": units,
        "coverage": coverage,
        "config": config,
        "identity": identity,
    }


def selected_run_units(
    units: list[dict[str, Any]], max_new_units: int
) -> list[dict[str, Any]]:
    """Scope preflight to a deterministic prefix, even when units are reused."""
    if max_new_units < 0:
        raise TranscriptionError("max_new_units must be non-negative")
    return units[:max_new_units] if max_new_units else units


def run_command(args: argparse.Namespace) -> int:
    if installed_google_genai_version() == "not-installed":
        raise TranscriptionError(
            "google-genai is not installed; install tools/harness/requirements_gemini.txt before starting a paid run"
        )
    context = build_context(args)
    workspace = Path(args.workspace).resolve()
    ensure_external_workspace(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or default_run_id(context["identity"], context["config"])
    store = (
        durable_media.LocalObjectStore(Path(args.local_store).resolve())
        if args.local_store
        else durable_media.RcloneObjectStore()
    )

    completed = verify_completion_marker(store, workspace / "marker_check", run_id)
    if completed is not None:
        if completed.get("input_identity") != context["identity"]:
            raise TranscriptionError("completion marker input identity does not match")
        if completed.get("config_sha256") != sha256_json(context["config"]):
            raise TranscriptionError("completion marker config does not match")
        print(json.dumps({"run_id": run_id, "state": "COMPLETED", "reused": True}, ensure_ascii=False))
        return 0

    run = open_or_create_run(
        store,
        workspace,
        context["identity"],
        context["config"],
        run_id,
        lease_seconds=args.lease_seconds,
        takeover=args.takeover,
    )
    durable_run_plan(run, workspace, context["units"], context["config"])
    client = new_genai_client()
    execution_units = selected_run_units(context["units"], args.max_new_units)
    new_count = 0
    for unit_index, unit in enumerate(execution_units):
        next_unit_id = (
            context["units"][unit_index + 1]["unit_id"]
            if unit_index + 1 < len(context["units"])
            else None
        )
        try:
            result = transcribe_one(
                run=run,
                workspace=workspace,
                source=context["source"],
                unit=unit,
                model=args.model,
                word_timestamps=args.word_timestamps,
                overlap_seconds=args.overlap_seconds,
                ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,
                client=client,
                allow_retry_ambiguous=args.allow_retry_ambiguous,
                next_unit_id=next_unit_id,
            )
        except Exception:
            try:
                pause_run(run)
            except Exception:
                pass
            raise
        print(f"{result} {unit['unit_id']}")
        if result == "TRANSCRIBED":
            new_count += 1

    if args.max_new_units:
        pause_run(run)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "state": "PREFLIGHT_STOP",
                    "planned_prefix_units": len(execution_units),
                    "new_units": new_count,
                    "next_unit": (
                        context["units"][len(execution_units)]["unit_id"]
                        if len(execution_units) < len(context["units"])
                        else None
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 0

    manifest = build_completion_manifest(
        run,
        context["units"],
        context["tracks"],
        context["probe"]["duration"],
        workspace,
    )
    commit_completion(run, workspace, manifest)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "state": "COMPLETED",
                "unit_count": len(context["units"]),
                "coverage": manifest["coverage"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def plan_command(args: argparse.Namespace) -> int:
    context = build_context(args)
    run_id = args.run_id or default_run_id(context["identity"], context["config"])
    print(
        json.dumps(
            {
                "run_id": run_id,
                "input_identity": context["identity"],
                "config": context["config"],
                "config_sha256": sha256_json(context["config"]),
                "coverage": context["coverage"],
                "unit_count": len(context["units"]),
                "units": context["units"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def status_command(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    ensure_external_workspace(workspace)
    store = (
        durable_media.LocalObjectStore(Path(args.local_store).resolve())
        if args.local_store
        else durable_media.RcloneObjectStore()
    )
    completed = verify_completion_marker(store, workspace / "status_marker", args.run_id)
    if completed is not None:
        print(json.dumps({"state": "COMPLETED", "manifest": completed}, ensure_ascii=False, indent=2))
        return 0
    journal = durable_media.read_journal(store, workspace / "status", args.run_id)
    print(json.dumps(journal, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser, *, workspace: bool) -> None:
        command.add_argument("--state", default=str(DEFAULT_STATE))
        command.add_argument("--source", help="explicit local primary recording path")
        command.add_argument("--model", default=DEFAULT_MODEL)
        command.add_argument("--chunk-seconds", type=float, default=DEFAULT_CHUNK_SECONDS)
        command.add_argument("--overlap-seconds", type=float, default=0.0)
        command.add_argument("--word-timestamps", action="store_true")
        command.add_argument("--ffmpeg", default="ffmpeg")
        command.add_argument("--ffprobe", default="ffprobe")
        command.add_argument("--run-id")
        if workspace:
            command.add_argument("--workspace", required=True)

    plan = sub.add_parser("plan", help="validate source and print deterministic run plan")
    common(plan, workspace=False)

    run = sub.add_parser("run", help="transcribe or resume the clean-room run")
    common(run, workspace=True)
    run.add_argument("--local-store", help="test-only/local durable store root")
    run.add_argument("--lease-seconds", type=float, default=900.0)
    run.add_argument("--takeover", action="store_true")
    run.add_argument("--max-new-units", type=int, default=0)
    run.add_argument("--allow-retry-ambiguous", action="store_true")

    status = sub.add_parser("status", help="read durable run status")
    status.add_argument("run_id")
    status.add_argument("--workspace", required=True)
    status.add_argument("--local-store")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "plan":
            return plan_command(args)
        if args.command == "run":
            return run_command(args)
        if args.command == "status":
            return status_command(args)
        raise TranscriptionError(f"unknown command: {args.command}")
    except (
        OSError,
        json.JSONDecodeError,
        material_store.MaterialStoreError,
        durable_media.DurableMediaError,
        TranscriptionError,
    ) as exc:
        print(f"FAIL — {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FAIL — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
