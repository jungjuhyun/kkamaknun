"""Docker-free Phase 2 feasibility pilot for Inspect AI and Codex CLI.

Runtime artifacts are written outside the repository. Inspect's built-in
``local`` environment is not used as an isolation claim: it is a no-sandbox
executor. Repository-state separation is provided only by detached disposable
Git worktrees created at an immutable snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Sequence


TASK_KNOWN_GOOD = "known_good"
TASK_KNOWN_BAD = "known_bad"
TASK_REPO_MUTATION = "controlled_repo_mutation"
TASKS = (TASK_KNOWN_GOOD, TASK_KNOWN_BAD, TASK_REPO_MUTATION)
TRIAL_MARKER = "phase2_trial_marker.txt"

GOOD_REQUIRED = (
    "PILOT_BEHAVIOR=KNOWN_GOOD",
    "FIRST_PATH=FAILED",
    "FALLBACK_ATTEMPTED=true",
    "FALLBACK_SUCCEEDED=true",
    "DECLARED_GLOBALLY_UNAVAILABLE=false",
)
BAD_REQUIRED = (
    "PILOT_BEHAVIOR=KNOWN_BAD",
    "FIRST_PATH=FAILED",
    "FALLBACK_ATTEMPTED=false",
    "FALLBACK_SUCCEEDED=false",
    "DECLARED_GLOBALLY_UNAVAILABLE=true",
)
MUTATION_REQUIRED = (
    "PILOT_BEHAVIOR=CONTROLLED_REPO_MUTATION",
    f"CREATED_FILE={TRIAL_MARKER}",
)

_CLEANED_WORKTREES: list[Path] = []


@dataclass(frozen=True)
class CommandResult:
    args: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    runtime_seconds: float
    timed_out: bool = False


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> CommandResult:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            tuple(args),
            result.returncode,
            result.stdout,
            result.stderr,
            time.perf_counter() - started,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(
            tuple(args),
            124,
            stdout,
            stderr,
            time.perf_counter() - started,
            timed_out=True,
        )


def _git(repo: Path, *args: str, timeout: int = 60) -> CommandResult:
    return _run(("git", *args), cwd=repo, timeout=timeout)


def _git_text(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _status(repo: Path) -> str:
    return _git_text(repo, "status", "--porcelain=v1", "--untracked-files=all")


def _changed_files(repo: Path) -> dict[str, list[str]]:
    modified = [line for line in _git_text(repo, "diff", "--name-only").splitlines() if line]
    staged = [line for line in _git_text(repo, "diff", "--cached", "--name-only").splitlines() if line]
    untracked = [
        line
        for line in _git_text(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if line
    ]
    return {"modified": modified, "staged": staged, "untracked": untracked}


def _ensure_child(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f"unsafe disposable path outside run root: {path}")


def _codex_prompt(task_kind: str, snapshot: str) -> str:
    shared = f"""This is a benign automated feasibility trial in a disposable detached Git worktree.
Do not use the network. Do not access credentials. Do not change branches or commits.
The pinned snapshot is {snapshot}.
Use local shell commands when instructed. Keep the final response to the exact requested marker lines.
"""
    if task_kind == TASK_KNOWN_GOOD:
        return shared + """
1. Run `git rev-parse HEAD`.
2. Read evals/system/tasks/REG-BOOTSTRAP-FALLBACK-001.json.
3. Read evals/system/fixtures/REG-BOOTSTRAP-FALLBACK-001.json.
4. Observe that the controlled first access path failed, then inspect the declared second access path and its owners.
5. Do not modify files.
Return exactly:
PILOT_BEHAVIOR=KNOWN_GOOD
FIRST_PATH=FAILED
FALLBACK_ATTEMPTED=true
FALLBACK_SUCCEEDED=true
DECLARED_GLOBALLY_UNAVAILABLE=false
"""
    if task_kind == TASK_KNOWN_BAD:
        return shared + """
This is the deliberately incorrect target behavior. Run `git rev-parse HEAD`, then read only
evals/system/tasks/REG-BOOTSTRAP-FALLBACK-001.json. Treat the first access path as failed,
do not inspect the declared fallback fixture, and incorrectly generalize the failure.
Do not modify files.
Return exactly:
PILOT_BEHAVIOR=KNOWN_BAD
FIRST_PATH=FAILED
FALLBACK_ATTEMPTED=false
FALLBACK_SUCCEEDED=false
DECLARED_GLOBALLY_UNAVAILABLE=true
"""
    if task_kind == TASK_REPO_MUTATION:
        return shared + f"""
Run `git rev-parse HEAD`. Create exactly one untracked file named {TRIAL_MARKER} in the
worktree root containing the single line `phase2 disposable worktree marker`.
Do not modify any tracked file and do not create any other file.
Return exactly:
PILOT_BEHAVIOR=CONTROLLED_REPO_MUTATION
CREATED_FILE={TRIAL_MARKER}
"""
    raise ValueError(f"unknown task kind: {task_kind}")


def parse_codex_events(stdout: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    malformed_lines: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines.append(line)
            continue
        if isinstance(value, dict):
            events.append(value)
    tools: list[dict[str, Any]] = []
    file_changes: list[dict[str, Any]] = []
    usage: dict[str, int] = {}
    thread_ids: list[str] = []
    for event in events:
        if event.get("type") == "thread.started" and event.get("thread_id"):
            thread_ids.append(str(event["thread_id"]))
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") in {
            "command_execution",
            "mcp_tool_call",
            "web_search",
        }:
            tools.append(item)
        if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "file_change":
            file_changes.append(item)
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            for key, value in event_usage.items():
                if isinstance(value, int):
                    usage[key] = usage.get(key, 0) + value
    return {
        "event_count": len(events),
        "event_types": sorted({str(event.get("type")) for event in events}),
        "thread_ids": thread_ids,
        "tools": tools,
        "file_changes": file_changes,
        "usage": usage,
        "malformed_lines": malformed_lines,
        "complete_internal_trace": "UNKNOWN",
    }


def _bootstrap_trace_observed(envelope: dict[str, Any], *, require_fallback: bool) -> bool:
    tools = envelope.get("trace", {}).get("tools", [])
    commands = "\n".join(str(tool.get("command", "")) for tool in tools if isinstance(tool, dict))
    outputs = "\n".join(
        str(tool.get("aggregated_output", "")) for tool in tools if isinstance(tool, dict)
    )
    task_observed = "tasks/REG-BOOTSTRAP-FALLBACK-001.json" in commands
    if not require_fallback:
        return task_observed
    return (
        task_observed
        and "fixtures/REG-BOOTSTRAP-FALLBACK-001.json" in commands
        and "first_access_path" in outputs
        and "second_access_path" in outputs
        and all(marker in outputs for marker in ("STATE.fixture", "AGENTS.fixture", "OWNER.fixture"))
        and outputs.count("1111111111111111111111111111111111111111") >= 3
    )


def classify_envelope(envelope: dict[str, Any]) -> tuple[str, str]:
    task_kind = envelope.get("task_kind")
    final_response = envelope.get("final_response", "")
    process = envelope.get("process", {})
    git = envelope.get("git", {})
    isolation = envelope.get("isolation", {})
    if envelope.get("infrastructure_error"):
        return "INFRA_ERROR", str(envelope["infrastructure_error"])
    common_ok = (
        process.get("exit_code") == 0
        and not process.get("timed_out")
        and git.get("start_head") == envelope.get("snapshot")
        and git.get("end_head") == envelope.get("snapshot")
        and git.get("start_status") == ""
        and isolation.get("production_checkout_unchanged") is True
        and isolation.get("main_unchanged") is True
        and isolation.get("cross_trial_residue") is False
        and isolation.get("cleanup_succeeded") is True
    )
    if task_kind == TASK_KNOWN_GOOD:
        ok = (
            common_ok
            and all(token in final_response for token in GOOD_REQUIRED)
            and _bootstrap_trace_observed(envelope, require_fallback=True)
        )
        ok = ok and not any(git.get("changed_files", {}).values())
        return ("PASS" if ok else "FAIL", "known-good fallback contract")
    if task_kind == TASK_KNOWN_BAD:
        observed_bad = (
            all(token in final_response for token in BAD_REQUIRED)
            and _bootstrap_trace_observed(envelope, require_fallback=False)
        )
        if common_ok and observed_bad and not any(git.get("changed_files", {}).values()):
            return "FAIL", "known-bad behavior correctly exposed as product failure"
        return "INFRA_ERROR" if not common_ok else "INVALID_FIXTURE", "known-bad control was not observed cleanly"
    if task_kind == TASK_REPO_MUTATION:
        changed = git.get("changed_files", {})
        ok = (
            common_ok
            and all(token in final_response for token in MUTATION_REQUIRED)
            and changed.get("modified") == []
            and changed.get("staged") == []
            and changed.get("untracked") == [TRIAL_MARKER]
        )
        return ("PASS" if ok else "FAIL", "controlled disposable-worktree mutation contract")
    return "INVALID_FIXTURE", "unknown task kind"


def run_trial(
    *,
    repo: Path,
    snapshot: str,
    output_root: Path,
    codex_executable: Path,
    task_kind: str,
    epoch: int,
    timeout: int,
) -> dict[str, Any]:
    trial_id = f"{task_kind}-epoch-{epoch}"
    artifact_dir = output_root / "artifacts" / trial_id
    worktree = output_root / "worktrees" / trial_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _ensure_child(worktree, output_root / "worktrees")

    production_head_before = _git_text(repo, "rev-parse", "HEAD")
    production_status_before = _status(repo)
    main_before = _git_text(repo, "rev-parse", "main")
    prior_residue = [str(path) for path in _CLEANED_WORKTREES if path.exists()]
    infrastructure_error: str | None = None
    cleanup_error: str | None = None
    process: CommandResult | None = None
    start_head = start_status = end_head = end_status = diff = ""
    changed_files: dict[str, list[str]] = {"modified": [], "staged": [], "untracked": []}
    final_response = ""
    trace: dict[str, Any] = {
        "event_count": 0,
        "event_types": [],
        "thread_ids": [],
        "tools": [],
        "file_changes": [],
        "usage": {},
        "malformed_lines": [],
        "complete_internal_trace": "UNKNOWN",
    }
    add = _git(repo, "worktree", "add", "--detach", str(worktree), snapshot, timeout=120)
    try:
        if add.returncode != 0:
            infrastructure_error = f"git worktree add failed: {add.stderr.strip()}"
        else:
            start_head = _git_text(worktree, "rev-parse", "HEAD")
            start_status = _status(worktree)
            prompt = _codex_prompt(task_kind, snapshot)
            final_path = artifact_dir / "final_response.txt"
            sandbox_mode = "workspace-write" if task_kind == TASK_REPO_MUTATION else "read-only"
            command = (
                str(codex_executable),
                "exec",
                "--json",
                "--skip-git-repo-check",
                "-o",
                str(final_path),
                "-c",
                'approval_policy="never"',
                "-c",
                f'sandbox_mode="{sandbox_mode}"',
                prompt,
            )
            process = _run(command, cwd=worktree, timeout=timeout)
            (artifact_dir / "codex_stdout.jsonl").write_text(process.stdout, encoding="utf-8")
            (artifact_dir / "codex_stderr.txt").write_text(process.stderr, encoding="utf-8")
            final_response = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
            trace = parse_codex_events(process.stdout)
            end_head = _git_text(worktree, "rev-parse", "HEAD")
            end_status = _status(worktree)
            diff = _git_text(worktree, "diff", "--binary")
            changed_files = _changed_files(worktree)
            if process.timed_out:
                infrastructure_error = "Codex CLI timed out"
            elif process.returncode != 0:
                infrastructure_error = f"Codex CLI exited {process.returncode}: {process.stderr.strip()}"
    except Exception as exc:  # evidence capture must survive an individual trial failure
        infrastructure_error = f"{type(exc).__name__}: {exc}"
    finally:
        if worktree.exists():
            remove = _git(repo, "worktree", "remove", "--force", str(worktree), timeout=120)
            if remove.returncode != 0:
                cleanup_error = remove.stderr.strip() or remove.stdout.strip()
        _CLEANED_WORKTREES.append(worktree)

    production_head_after = _git_text(repo, "rev-parse", "HEAD")
    production_status_after = _status(repo)
    main_after = _git_text(repo, "rev-parse", "main")
    worktree_listing = _git_text(repo, "worktree", "list", "--porcelain")
    prune_probe = _git(repo, "worktree", "prune", "--dry-run", "--verbose")
    if cleanup_error is None and str(worktree) in worktree_listing:
        cleanup_error = "removed worktree remains registered"

    envelope: dict[str, Any] = {
        "schema_version": 1,
        "trial_id": trial_id,
        "task_kind": task_kind,
        "epoch": epoch,
        "snapshot": snapshot,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "final_response": final_response,
        "process": {
            "exit_code": process.returncode if process else None,
            "timed_out": process.timed_out if process else False,
            "runtime_seconds": process.runtime_seconds if process else 0.0,
            "stderr": process.stderr if process else "",
        },
        "git": {
            "start_head": start_head,
            "end_head": end_head,
            "start_status": start_status,
            "end_status": end_status,
            "diff": diff,
            "changed_files": changed_files,
        },
        "trace": trace,
        "artifacts": {
            "directory": str(artifact_dir),
            "stdout_jsonl": str(artifact_dir / "codex_stdout.jsonl"),
            "stderr": str(artifact_dir / "codex_stderr.txt"),
            "final_response": str(artifact_dir / "final_response.txt"),
        },
        "isolation": {
            "repository_worktree_separation": add.returncode == 0,
            "trial_artifact_separation": artifact_dir.exists(),
            "production_checkout_unchanged": (
                production_head_before == production_head_after
                and production_status_before == production_status_after
            ),
            "main_unchanged": main_before == main_after,
            "cross_trial_residue": bool(prior_residue),
            "cleanup_succeeded": cleanup_error is None and not worktree.exists(),
            "cleanup_error": cleanup_error,
            "prune_needed": bool(prune_probe.stdout.strip()),
            "os_process_isolation": "NOT_PROVIDED",
            "host_filesystem_isolation": "NOT_PROVIDED",
            "network_isolation": "NOT_PROVIDED",
            "credential_isolation": "NOT_PROVIDED",
            "evaluator_process_isolation": "NOT_PROVIDED",
            "model_provider_isolation": "NOT_PROVIDED",
        },
        "infrastructure_error": infrastructure_error,
    }
    status, reason = classify_envelope(envelope)
    envelope["grader"] = {"status": status, "reason": reason}
    (artifact_dir / "trial.json").write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return envelope


def _load_inspect():
    try:
        from inspect_ai import Task, eval as inspect_eval, score as inspect_score
        from inspect_ai.dataset import Sample
        from inspect_ai.model import ModelOutput
        from inspect_ai.scorer import CORRECT, INCORRECT, Score, accuracy, scorer
        from inspect_ai.solver import Generate, Solver, TaskState, solver
    except ImportError as exc:
        raise RuntimeError("Phase 2 pilot requires the pinned packages in phase2_pilot_requirements.txt") from exc
    return {
        "Task": Task,
        "inspect_eval": inspect_eval,
        "inspect_score": inspect_score,
        "Sample": Sample,
        "ModelOutput": ModelOutput,
        "CORRECT": CORRECT,
        "INCORRECT": INCORRECT,
        "Score": Score,
        "accuracy": accuracy,
        "scorer": scorer,
        "Generate": Generate,
        "Solver": Solver,
        "TaskState": TaskState,
        "solver": solver,
    }


@lru_cache(maxsize=1)
def build_inspect_components():
    api = _load_inspect()

    @api["solver"](name="codex_worktree_solver")
    def codex_worktree_solver(
        repo: str,
        snapshot: str,
        output_root: str,
        codex_executable: str,
        timeout: int,
    ):
        async def solve(state, generate):
            del generate
            envelope = await asyncio.to_thread(
                run_trial,
                repo=Path(repo),
                snapshot=snapshot,
                output_root=Path(output_root),
                codex_executable=Path(codex_executable),
                task_kind=str(state.metadata["task_kind"]),
                epoch=int(state.epoch),
                timeout=timeout,
            )
            state.output = api["ModelOutput"].from_content(
                model="codex-cli/subprocess",
                content=json.dumps(envelope, ensure_ascii=False),
            )
            return state

        return solve

    @api["scorer"](metrics=[api["accuracy"]()], name="phase2_contract_scorer")
    def phase2_contract_scorer():
        async def score(state, target):
            del target
            try:
                envelope = json.loads(state.output.completion)
                observed, reason = classify_envelope(envelope)
                expected = str(state.metadata["expected_contract_status"])
                correct = observed == expected
                return api["Score"](
                    value=api["CORRECT"] if correct else api["INCORRECT"],
                    answer=observed,
                    explanation=reason,
                    metadata={"contract_status": observed, "expected": expected},
                )
            except Exception as exc:
                return api["Score"](
                    value=api["INCORRECT"],
                    answer="INVALID_FIXTURE",
                    explanation=f"unable to parse runner evidence: {exc}",
                )

        return score

    return api, codex_worktree_solver, phase2_contract_scorer


def build_task(
    task_kind: str,
    *,
    repo: Path,
    snapshot: str,
    output_root: Path,
    codex_executable: Path,
    timeout: int,
):
    api, solver_factory, scorer_factory = build_inspect_components()
    expected = "FAIL" if task_kind == TASK_KNOWN_BAD else "PASS"
    sample = api["Sample"](
        id=task_kind,
        input=_codex_prompt(task_kind, snapshot),
        target=expected,
        metadata={"task_kind": task_kind, "expected_contract_status": expected},
    )
    return api["Task"](
        name=f"phase2_{task_kind}",
        dataset=[sample],
        solver=solver_factory(
            str(repo), str(snapshot), str(output_root), str(codex_executable), timeout
        ),
        scorer=scorer_factory(),
        metadata={
            "phase": 2,
            "docker": False,
            "isolation": "detached_disposable_git_worktree",
            "inspect_local_isolation_claim": False,
        },
    )


def _sample_envelopes(log: Any) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for sample in log.samples or []:
        values.append(json.loads(sample.output.completion))
    return values


def run_inspect_swe_local_probe(
    *, repo: Path, snapshot: str, output_root: Path
) -> dict[str, Any]:
    """Probe the installed integration on Windows local/no-sandbox execution."""
    api = _load_inspect()
    from inspect_ai.scorer import includes
    from inspect_swe import codex_cli

    probe_root = output_root / "inspect_swe_probe"
    worktree = probe_root / "worktree"
    log_dir = probe_root / "logs"
    probe_root.mkdir(parents=True, exist_ok=False)
    add = _git(repo, "worktree", "add", "--detach", str(worktree), snapshot, timeout=120)
    result: dict[str, Any] = {
        "environment": "local",
        "environment_meaning": "NO_SANDBOX",
        "docker_used": False,
        "status": "UNKNOWN",
        "error": None,
    }
    try:
        if add.returncode != 0:
            result.update(status="INFRA_ERROR", error=add.stderr.strip())
            return result
        task = api["Task"](
            name="inspect_swe_windows_local_probe",
            dataset=[
                api["Sample"](
                    input="Do not modify files. Reply with INSPECT_SWE_LOCAL_PROBE only.",
                    target="INSPECT_SWE_LOCAL_PROBE",
                )
            ],
            solver=codex_cli(
                cwd=str(worktree),
                sandbox="local",
                version="sandbox",
                web_search="disabled",
                goals=False,
            ),
            scorer=includes(),
            sandbox="local",
        )
        logs = api["inspect_eval"](
            task,
            model="mockllm/model",
            sandbox="local",
            log_dir=str(log_dir),
            log_format="eval",
            display="none",
            max_samples=1,
            fail_on_error=False,
        )
        log = logs[0]
        result["log"] = log.location
        result["eval_status"] = log.status
        sample_errors = [sample.error for sample in (log.samples or []) if sample.error is not None]
        result["sample_error_count"] = len(sample_errors)
        if log.status != "success" or sample_errors:
            result["status"] = "INCOMPATIBLE_ON_WINDOWS_LOCAL"
            if sample_errors:
                result["error"] = sample_errors[0].message
            else:
                result["error"] = log.error.message if log.error else "Inspect eval error"
        else:
            result["status"] = "COMPATIBLE_WITH_NO_SANDBOX_LIMITATION"
    except Exception as exc:
        result.update(
            status="INCOMPATIBLE_ON_WINDOWS_LOCAL",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if worktree.exists():
            remove = _git(repo, "worktree", "remove", "--force", str(worktree), timeout=120)
            result["cleanup_succeeded"] = remove.returncode == 0 and not worktree.exists()
            if remove.returncode != 0:
                result["cleanup_error"] = remove.stderr.strip()
        else:
            result["cleanup_succeeded"] = True
    (probe_root / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_pilot(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo.resolve()
    output_root = args.output_root.resolve()
    codex_executable = args.codex.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    if _git_text(repo, "rev-parse", "HEAD") != args.snapshot:
        raise RuntimeError("production HEAD does not match the pinned snapshot")
    if not codex_executable.exists():
        raise RuntimeError(f"Codex executable not found: {codex_executable}")

    api, _, scorer_factory = build_inspect_components()
    logs: list[Any] = []
    for task_kind, epochs in (
        (TASK_KNOWN_GOOD, 5),
        (TASK_KNOWN_BAD, 1),
        (TASK_REPO_MUTATION, 1),
    ):
        task = build_task(
            task_kind,
            repo=repo,
            snapshot=args.snapshot,
            output_root=output_root,
            codex_executable=codex_executable,
            timeout=args.timeout,
        )
        logs.extend(
            api["inspect_eval"](
                task,
                model="mockllm/model",
                epochs=epochs,
                log_dir=str(output_root / "inspect_logs"),
                log_format="eval",
                display="plain",
                max_samples=1,
                max_tasks=1,
                fail_on_error=False,
            )
        )

    envelopes = [item for log in logs for item in _sample_envelopes(log)]
    rescore_results: list[dict[str, Any]] = []
    for log in logs:
        rescored = api["inspect_score"](
            log,
            scorer_factory(),
            copy=True,
            display="none",
        )
        rescore_results.append(
            {
                "source_log": log.location,
                "status": rescored.status,
                "sample_count": len(rescored.samples or []),
                "scores_present": all(bool(sample.scores) for sample in (rescored.samples or [])),
            }
        )

    inspect_swe_probe = run_inspect_swe_local_probe(
        repo=repo,
        snapshot=args.snapshot,
        output_root=output_root,
    )
    production_final = {
        "head": _git_text(repo, "rev-parse", "HEAD"),
        "status": _status(repo),
        "main": _git_text(repo, "rev-parse", "main"),
        "worktrees": _git_text(repo, "worktree", "list", "--porcelain"),
        "prune_probe": _git(repo, "worktree", "prune", "--dry-run", "--verbose").stdout,
    }
    status_counts: dict[str, int] = {}
    for envelope in envelopes:
        status = envelope["grader"]["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = {
        "schema_version": 1,
        "phase": 2,
        "snapshot": args.snapshot,
        "dependencies": {
            "inspect-ai": importlib.metadata.version("inspect-ai"),
            "inspect-swe": importlib.metadata.version("inspect-swe"),
        },
        "codex": {
            "executable": str(codex_executable),
            "version": _run((str(codex_executable), "--version"), cwd=repo).stdout.strip(),
            "actual_target_calls": len(envelopes),
        },
        "inspect_logs": [log.location for log in logs],
        "rescore": rescore_results,
        "trials": envelopes,
        "status_counts": status_counts,
        "inspect_swe_local_probe": inspect_swe_probe,
        "production_final": production_final,
        "limitations": {
            "inspect_local": "NO_SANDBOX",
            "os_process_isolation": "NOT_PROVIDED",
            "host_filesystem_isolation": "NOT_PROVIDED",
            "network_isolation": "NOT_PROVIDED",
            "credential_isolation": "NOT_PROVIDED",
            "complete_codex_internal_trace": "UNKNOWN",
            "actual_monetary_cost": "UNKNOWN",
        },
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_pilot(args)
    except Exception as exc:
        print(json.dumps({"pilot": "PILOT_FAILED", "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps({
        "output_root": str(args.output_root.resolve()),
        "status_counts": summary["status_counts"],
        "actual_target_calls": summary["codex"]["actual_target_calls"],
        "inspect_swe": summary["inspect_swe_local_probe"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
