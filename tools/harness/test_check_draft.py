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

A = LOCK["잠금_문장"]["A"]
B = LOCK["잠금_문장"]["B"]
CLEAN = f"A: `{A}`\nB: \"{B}\"\n실제 촬영물의 사건과 반응을 바탕으로 기획한다.\n"


def run(text):
    return check(text, COMMON, LOCK)


def test_default_lock_resolves_from_state():
    assert resolve_lock_path().resolve() == (HERE / "EP1_LOCK.json").resolve()


def test_clean_material_first_draft_passes():
    assert run(CLEAN) == []


def test_locked_b_redesign_is_caught():
    text = CLEAN.replace(B, "B 후보 3개를 비교한다: 레제편 / 귀멸 / 팟캐스트")
    assert any("잠금 B" in fail for fail in run(text))


def test_unowned_subtitle_body_claim_is_caught():
    text = CLEAN + "레제편 일본어 자막 본문을 확보해 대조했다.\n"
    assert any("자막 본문" in fail for fail in run(text))


def test_existing_footage_denial_is_caught():
    text = CLEAN + "아직 촬영한 것이 없으니 장면을 가정한다.\n"
    assert any("촬영" in fail for fail in run(text))


def test_simulation_sentence_is_not_required_anymore():
    # 현재 1화는 material-first이므로 과거 POC의 시뮬레이션 경계 문장을 강제하지 않는다.
    assert run(CLEAN) == []


def test_quality_is_outside_validator_scope():
    # 재미·중간 엔진·RED TEAM 수행 여부는 문자열 검사기로 품질 인증하지 않는다.
    assert run(CLEAN + "이 구조는 무조건 재미있고 시청지속도 완벽하다.\n") == []


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
