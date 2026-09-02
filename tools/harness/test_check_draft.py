"""STATE.md 실패 목록 5개를 초안으로 재현해 check_draft.py가 잡는지 기록한다.

실행: python -m pytest tools/harness/test_check_draft.py -q
      또는 python tools/harness/test_check_draft.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from check_draft import check  # noqa: E402

COMMON = json.loads((HERE / "COMMON_RULES.json").read_text(encoding="utf-8"))
LOCK = json.loads((HERE / "EP0_LOCK.json").read_text(encoding="utf-8"))

A = LOCK["잠금_문장"]["A"]
B = LOCK["잠금_문장"]["B"]
SIM, REAL = COMMON["출처_선언_하나만"]
CLEAN = f"A: `{A}`\nB: \"{B}\"\n{SIM}\n| 클립화면 | 나레이션 |\n|---|---|\n| 첫 장면 | 무음 |\n"


def run(text):
    return check(text, COMMON, LOCK)


def test_clean_draft_passes():
    assert run(CLEAN) == []


def test_fail1_b_redesigned():
    # 실패 1: 확정된 B를 다시 설계 대상으로 삼음 → B 원문이 사라지므로 잡힘
    text = CLEAN.replace(B, "B 후보 3개를 비교한다: 레제편 / 귀멸 / 팟캐스트")
    assert any("잠금 B" in f for f in run(text))


def test_fail2_subtitle_body_claimed():
    # 실패 2: 자막 존재 확인과 본문 확보 혼동 → 금지 표현으로 잡힘
    text = CLEAN + "레제편 일본어 자막 본문을 확보해 대조했다.\n"
    assert any("자막 본문을 확보" in f for f in run(text))


def test_fail3_simulation_boundary_dropped():
    # 실패 3: 시뮬레이션 경계 상실 → 필수 문장 누락으로 잡힘 (경계 문장이 있으면서 흔드는 경우는 사람 판정)
    text = CLEAN.replace(SIM, "이 반응은 실제 촬영에서 확인됐다.")
    assert any("출처 선언 없음" in f for f in run(text))


def test_fail4_process_skipped_not_machine_checkable():
    # 실패 4: RED TEAM·왜 봐야 하는가 공정이 출력 전에 작동 안 함 → 검사기 범위 밖. PASS 줄 관문(지침 3)과 PIPELINE 6단계가 담당
    assert run(CLEAN) == []


def test_fail5_web_unverified_not_machine_checkable():
    # 실패 5: 웹 확인 없이 유튜브 지침 인용 → 검사기 범위 밖. PIPELINE 4단계 검수 기준(사람/AI 판정)
    assert run(CLEAN + "유튜브는 첫 30초 이탈률을 본다.\n") == []


def test_real_event_declaration_alone_passes():
    # 2026-09-03 실제 실패: 실제 사건 초안이 시뮬레이션 필수 문장에 걸림 → 출처 선언 택일
    assert run(CLEAN.replace(SIM, REAL)) == []


def test_both_declarations_fail():
    text = CLEAN + REAL + "\n"
    assert any("둘 다 있음" in f for f in run(text))


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError:
                fails += 1
                print("FAIL", name)
    sys.exit(1 if fails else 0)
