"""Deterministic validator behavior and shared pipeline structure regressions."""

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from check_draft import check, resolve_lock_path  # noqa: E402

COMMON = json.loads((HERE / "COMMON_RULES.json").read_text(encoding="utf-8"))
LOCK = json.loads((HERE / "EP1_LOCK.json").read_text(encoding="utf-8"))
STATE = json.loads((HERE / "STATE.json").read_text(encoding="utf-8"))
PIPELINE_TEXT = (HERE / "PIPELINE.yaml").read_text(encoding="utf-8")
PIPELINE = yaml.safe_load(PIPELINE_TEXT)

A = LOCK["잠금_문장"]["A"]
B = LOCK["잠금_문장"]["B"]
CLEAN = f'A: `{A}`\nB: "{B}"\n'


def run(text):
    return check(text, COMMON, LOCK)


def stages():
    return {stage["번호"]: stage for stage in PIPELINE["단계"]}


def test_default_lock_resolves_from_state():
    assert STATE["현재_lock"] == "tools/harness/EP1_LOCK.json"
    assert resolve_lock_path().resolve() == (HERE / "EP1_LOCK.json").resolve()


def test_clean_material_first_draft_passes():
    assert run(CLEAN) == []


def test_locked_premise_is_enforced():
    for original, replacement in {
        A: "다른 A",
        B: "다른 B",
    }.items():
        assert run(CLEAN.replace(original, replacement))


def test_forbidden_claims_are_enforced():
    assert run(CLEAN + "아직 촬영한 것이 없으니 장면을 가정한다.\n")


def test_subjective_quality_is_outside_validator_scope():
    assert run(CLEAN + "이 구조는 무조건 재미있고 시청지속도 완벽하다.\n") == []


def test_cleanroom_lock_does_not_preserve_old_planning():
    assert LOCK["입력_경로"] == "material_first"
    assert set(LOCK["잠금_문장"]) == {"A", "B"}
    assert LOCK["패키징_제약"]["exact_copy_locked"] is False
    assert "C" not in LOCK["잠금_문장"]
    assert "패키징_promise" not in LOCK["잠금_문장"]
    assert "타임라인" not in LOCK["잠금_문장"]
    assert {"planning_revision", "body_lock", "review_pilot_lock"}.isdisjoint(LOCK)


def test_runtime_registry_is_raw_material_only():
    artifacts = set(STATE["external_material"]["artifacts"])
    assert artifacts == {"ep1.primary_recording", "ep1.source_subtitles_ko"}
    assert STATE["상태"] == "EP1_CLEANROOM_GEMINI_RETRANSCRIPTION_PENDING"


def test_pipeline_topology_and_input_branches_are_preserved():
    assert PIPELINE["공정"] == "video_planning"
    assert list(PIPELINE["입력_분기"]) == ["material_first", "pre_shoot"]
    assert [stage["번호"] for stage in PIPELINE["단계"]] == list(range(1, 11))


def test_material_first_and_pre_shoot_share_stage_three():
    stage_three = stages()[3]
    assert set(stage_three["경로"]) == {"material_first", "pre_shoot"}
    for branch in stage_three["경로"].values():
        assert branch["하는_일"]
        assert branch["통과_조건"]


def test_opening_viewer_question_render_and_uat_gates_exist():
    stage_four = stages()[4]
    stage_nine = stages()[9]
    stage_ten = stages()[10]
    anatomy_fields = {next(iter(item)) for item in stage_four["해부_항목"]}
    assert {"Opening", "Viewer_Question"}.issubset(anatomy_fields)
    assert {"Opening", "Viewer Question"}.issubset(stage_nine["전문_평가_축"])
    assert stage_nine["render_금지_gate"]
    assert len(stage_ten["순서"]) == 4
    verdicts = {next(iter(item)) for item in stage_ten["판정_분리"]}
    assert verdicts == {
        "current truth·공정 위반이 남음",
        "공정은 지켰지만 영상이 약함",
        "최소 제작 가능 수준 이상",
    }
    assert stage_ten["통과_조건"]


def test_pipeline_has_no_episode_specific_count_or_fixed_pilot_duration():
    assert "청해 사례만 세 개 이상" not in PIPELINE_TEXT
    assert "2~3분 review pilot" not in PIPELINE_TEXT
    assert "2~3분 pilot" not in PIPELINE_TEXT


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError:
                failures += 1
                print("FAIL", name)
    sys.exit(1 if failures else 0)
