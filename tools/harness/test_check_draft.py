"""check_draft.py의 deterministic 범위와 현재 lock 라우팅을 검증한다.

실행:
    python -m pytest tools/harness/test_check_draft.py -q
    또는 python tools/harness/test_check_draft.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from check_draft import check, resolve_lock_path  # noqa: E402

COMMON = json.loads((HERE / "COMMON_RULES.json").read_text(encoding="utf-8"))
LOCK = json.loads((HERE / "EP1_LOCK.json").read_text(encoding="utf-8"))
PIPELINE_TEXT = (HERE / "PIPELINE.yaml").read_text(encoding="utf-8")

A = LOCK["잠금_문장"]["A"]
B = LOCK["잠금_문장"]["B"]
C = LOCK["잠금_문장"]["C"]
TIMELINE = LOCK["잠금_문장"]["타임라인"]
CLEAN = f"A: `{A}`\nB: \"{B}\"\nC: `{C}`\n타임라인: `{TIMELINE}`\n실제 촬영물의 사건과 반응을 바탕으로 기획한다.\n"


def run(text):
    return check(text, COMMON, LOCK)


def test_default_lock_resolves_from_state():
    assert resolve_lock_path().resolve() == (HERE / "EP1_LOCK.json").resolve()


def test_clean_material_first_draft_passes():
    assert run(CLEAN) == []


def test_locked_b_redesign_is_caught():
    text = CLEAN.replace(B, "B 후보 3개를 비교한다: 레제편 / 귀멸 / 팟캐스트")
    assert any("잠금 B" in fail for fail in run(text))


def test_locked_c_redesign_is_caught():
    text = CLEAN.replace(C, "나는 일본어를 완벽하게 알아듣는다.")
    assert any("잠금 C" in fail for fail in run(text))


def test_unowned_subtitle_body_claim_is_caught():
    text = CLEAN + "영화 전체 일본어 자막을 완전히 확보했다.\n"
    assert any("영화 전체 자막" in fail for fail in run(text))


def test_existing_footage_denial_is_caught():
    text = CLEAN + "아직 촬영한 것이 없으니 장면을 가정한다.\n"
    assert any("촬영" in fail for fail in run(text))


def test_simulation_sentence_is_not_required_anymore():
    # 현재 1화는 material-first이므로 과거 POC의 시뮬레이션 경계 문장을 강제하지 않는다.
    assert run(CLEAN) == []


def test_quality_is_outside_validator_scope():
    # 재미·중간 엔진·RED TEAM 수행 여부는 문자열 검사기로 품질 인증하지 않는다.
    assert run(CLEAN + "이 구조는 무조건 재미있고 시청지속도 완벽하다.\n") == []


def test_step5_separates_professional_judgment_from_viewer_observation():
    assert "이름: AI 전문 기획 판정" in PIPELINE_TEXT
    assert "단계: review rough cut 생성" in PIPELINE_TEXT
    assert "단계: 사용자 시청 테스트" in PIPELINE_TEXT
    assert "단계: AI 사후 해석" in PIPELINE_TEXT
    assert "최종 제작 진행 여부의 의사결정은 사용자에게 남긴다" in PIPELINE_TEXT
    assert "사용자는 \"실제로 만들어볼 수 있는가\", \"시청자라면 계속 볼 것 같은가\"를 최종 판정한다" not in PIPELINE_TEXT


def test_step5_keeps_quality_outside_deterministic_validator():
    assert "판정자: validator + AI/harness" in PIPELINE_TEXT
    assert "같은 AI의 RED TEAM PASS만으로 \"좋은 기획\"이라고 선언하지 않는다" in PIPELINE_TEXT


def test_step5_keeps_provenance_internal_without_forcing_overlay():
    assert "재확인·재시청·재촬영 여부는 내부 material provenance와 분석 기록에 보존" in PIPELINE_TEXT
    assert "viewer-facing 영상에 표시를 강제하지 않는다" in PIPELINE_TEXT
    assert "최초 반응이 아닌 장면을 `첫 반응`, `처음 본 순간`, `처음 보는 장면`이라고 명시적으로 주장하지 않는다" in PIPELINE_TEXT
    assert "재확인·재시청 사실을 숨기지 않고 표시" not in PIPELINE_TEXT


def test_material_first_reconstructs_independent_source_layers_before_candidates():
    assert "A source narrative, B desktop dialogue/audio, C user mic raw, D visual/nonverbal reaction" in PIPELINE_TEXT
    assert "synchronized evidence timeline을 만든 뒤에만 scene candidate 경쟁" in PIPELINE_TEXT
    assert "MUST_KEEP / BRIDGE / OPTIONAL" in PIPELINE_TEXT


def test_body_precedes_cold_open_and_continuity_is_distinct_from_chronology():
    assert "Cold open보다 본편을 먼저 설계한다" in PIPELINE_TEXT
    assert "chronology integrity와 narrative continuity를 별도로 검사" in PIPELINE_TEXT
    assert "Cold open/body의 동일 대사·reaction이 새 의미 없이 단순 반복되지 않는다" in PIPELINE_TEXT


def test_pre_render_quality_gate_blocks_known_review_b_failure_modes():
    assert "render_금지_gate:" in PIPELINE_TEXT
    assert "MUST_KEEP narrative beat가 누락됐다" in PIPELINE_TEXT
    assert "청해 사례만 세 개 이상 연속돼 진단표처럼 느껴진다" in PIPELINE_TEXT
    assert "작품 감상보다 analysis tag 순서가 편집을 지배한다" in PIPELINE_TEXT
    assert "하나라도 FAIL이면 review rough cut으로 넘기지 않고" in PIPELINE_TEXT


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
