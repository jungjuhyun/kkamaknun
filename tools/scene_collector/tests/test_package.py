"""app.py 화면 구조 시험.

NiceGUI를 실제로 띄우지 않고 app.py 소스를 ast와 문자열로만 검사한다.
각 계약은 `_check_...` 함수 하나로 두고, 같은 함수에 원본을 넣는 시험과
메모리에서만 변형한 소스를 넣어 실패를 잡는지 보는 변이 시험을 함께 둔다.
어떤 경우에도 app.py 파일 자체는 건드리지 않는다.
"""

import ast
from pathlib import Path

import pytest

import scene_collector

_SCENE_BOXES = ("saved_box", "scene_list_box", "detail_box", "local_box")


def test_package_is_importable() -> None:
    assert scene_collector.__name__ == "scene_collector"


def _app_source_text() -> str:
    app_file = Path(scene_collector.__file__).parent / "app.py"
    return app_file.read_text(encoding="utf-8")


def _app_source_tree(source: str | None = None) -> ast.Module:
    return ast.parse(_app_source_text() if source is None else source)


def _mutate(old: str, new: str) -> str:
    """app.py 원본을 메모리에서만 바꾼 소스를 돌려준다. 파일은 수정하지 않는다.

    기준 문자열이 정확히 한 번 나오지 않으면 변이 시험이 헛돌고 있는 것이므로
    그 자리에서 실패시킨다.
    """
    source = _app_source_text()
    found = source.count(old)
    assert found == 1, f"변이 기준 문자열이 {found}번 나왔습니다(1번이어야 함): {old!r}"
    return source.replace(old, new)


def _function_def(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """중첩된 함수까지 포함해 이름으로 함수 정의 하나를 찾는다."""
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"함수 정의 {name}을(를) 정확히 하나 찾지 못했습니다: {len(matches)}개"
    return matches[0]


def _call_names(node: ast.AST) -> list[str]:
    """노드 안에서 호출되는 함수 이름을 점 표기(obj.attr)로 모은다."""
    names: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.append(func.id)
        elif isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                names.append(f"{func.value.id}.{func.attr}")
            else:
                names.append(func.attr)
    return names


def _ui_labels(tree: ast.Module, widget: str | None = None) -> list[str]:
    """`ui.<widget>(...)`의 첫 인자로 쓰인 문자열 라벨을 모은다.

    widget이 None이면 ui.* 위젯 전부를 본다. 문서 문자열이나 안내 문장 같은
    일반 산문은 위젯 라벨이 아니므로 걸리지 않는다.
    """
    return [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (widget is None or node.func.attr == widget)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]


def _set_visibility_calls(node: ast.AST) -> list[tuple[str, object]]:
    """노드 안의 `<대상>.set_visibility(<상수>)` 호출을 (대상, 값)으로 모은다."""
    calls: list[tuple[str, object]] = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "set_visibility"
            and isinstance(child.func.value, ast.Name)
            and child.args
            and isinstance(child.args[0], ast.Constant)
        ):
            calls.append((child.func.value.id, child.args[0].value))
    return calls


def _nonlocal_names(tree: ast.Module) -> set[str]:
    return {
        name for node in ast.walk(tree) if isinstance(node, ast.Nonlocal) for name in node.names
    }


# ----------------------------------------------------------------------
# 기존 계약: 플레이어는 하나뿐이고 source만 바꾼다
# ----------------------------------------------------------------------


def test_app_creates_exactly_one_video_player() -> None:
    """장면 수만큼 플레이어를 만들지 않는다. ui.video 생성은 화면 전체에서 한 곳뿐이다."""
    tree = _app_source_tree()
    created = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "video"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
    ]
    assert len(created) == 1


def test_app_switches_the_existing_player_source_for_the_chosen_scene() -> None:
    """장면을 고르면 새 플레이어를 만들지 않고 하나뿐인 플레이어의 source만 바꾼다."""
    tree = _app_source_tree()
    set_source_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_source"
    ]
    assert len(set_source_calls) == 1


# ----------------------------------------------------------------------
# [수정 1] 중복 버튼 제거 · 표현 찾기 한 번에 조회+생성
# ----------------------------------------------------------------------


def _check_no_duplicate_generate_button(source: str) -> None:
    """"AI로 표현 생성" 버튼은 사라지고 "표현 찾기"/"표현 더 찾기"만 남는다."""
    tree = _app_source_tree(source)
    buttons = _ui_labels(tree, "button")
    assert "AI로 표현 생성" not in buttons
    # 다른 위젯 종류로 옮겨 붙여도 안 된다.
    assert "AI로 표현 생성" not in _ui_labels(tree)
    assert "표현 찾기" in buttons
    assert "표현 더 찾기" in buttons


def test_app_has_no_separate_ai_generate_button() -> None:
    _check_no_duplicate_generate_button(_app_source_text())


def test_duplicate_generate_button_check_catches_a_readded_button() -> None:
    """"표현 더 찾기" 옆에 예전 버튼을 되살리면 검사가 실패해야 한다."""
    mutated = _mutate(
        '                more_button = ui.button("표현 더 찾기"',
        '                ui.button("AI로 표현 생성", on_click=lambda: do_generate())\n'
        '                more_button = ui.button("표현 더 찾기"',
    )
    with pytest.raises(AssertionError):
        _check_no_duplicate_generate_button(mutated)


def test_duplicate_generate_button_check_catches_a_renamed_lookup_button() -> None:
    """"표현 찾기" 버튼이 사라져도 검사가 실패해야 한다."""
    mutated = _mutate(
        'lookup_button = ui.button("표현 찾기"',
        'lookup_button = ui.button("AI로 표현 생성"',
    )
    with pytest.raises(AssertionError):
        _check_no_duplicate_generate_button(mutated)


def _check_lookup_uses_lookup_or_generate(source: str) -> None:
    """do_lookup은 조회+생성을 한 번에 하는 함수만 부른다."""
    tree = _app_source_tree(source)
    calls = _call_names(_function_def(tree, "do_lookup"))
    assert "ui_controller.lookup_or_generate_expressions" in calls
    assert "ui_controller.lookup_expressions" not in calls
    assert "ui_controller.generate_more_expressions" not in calls


def test_do_lookup_calls_lookup_or_generate_expressions() -> None:
    _check_lookup_uses_lookup_or_generate(_app_source_text())


def test_lookup_flow_check_catches_the_old_lookup_only_call() -> None:
    mutated = _mutate(
        "ui_controller.lookup_or_generate_expressions(",
        "ui_controller.lookup_expressions(",
    )
    with pytest.raises(AssertionError):
        _check_lookup_uses_lookup_or_generate(mutated)


# ----------------------------------------------------------------------
# [수정 2] 의미·표현을 바꾸면 장면 화면을 전부 비운다
# ----------------------------------------------------------------------


def _check_scene_screen_is_cleared_on_both_entries(source: str) -> None:
    """do_lookup과 select_relation 둘 다 clear_scene_screen을 부른다."""
    tree = _app_source_tree(source)
    _function_def(tree, "clear_scene_screen")
    for name in ("do_lookup", "select_relation"):
        assert "clear_scene_screen" in _call_names(_function_def(tree, name)), name


def test_lookup_and_relation_selection_both_clear_the_scene_screen() -> None:
    _check_scene_screen_is_cleared_on_both_entries(_app_source_text())


def test_clear_call_check_catches_a_missing_clear_in_select_relation() -> None:
    mutated = _mutate(
        "clear_scene_screen()\n        state.start_relation(chosen)",
        "state.start_relation(chosen)",
    )
    with pytest.raises(AssertionError):
        _check_scene_screen_is_cleared_on_both_entries(mutated)


def _check_clear_scene_screen_resets_everything(source: str) -> None:
    """clear_scene_screen이 상태·플레이어·장면 표시 상자를 모두 비운다."""
    node = _function_def(_app_source_tree(source), "clear_scene_screen")
    calls = _call_names(node)
    assert "state.clear" in calls
    assert "ui_controller.reset_player" in calls
    assert ("player_box", False) in _set_visibility_calls(node)
    for box in _SCENE_BOXES:
        assert f"{box}.clear" in calls, box


def test_clear_scene_screen_resets_state_player_and_every_box() -> None:
    _check_clear_scene_screen_resets_everything(_app_source_text())


@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        ("        ui_controller.reset_player(player)\n", ""),
        ("        state.clear()\n", ""),
        ("        player_box.set_visibility(False)\n", ""),
        ("        local_box.clear()\n", ""),
    ],
)
def test_clear_scene_screen_check_catches_each_missing_reset(
    anchor: str, replacement: str
) -> None:
    """초기화 한 줄만 빠져도 검사가 실패해야 한다."""
    with pytest.raises(AssertionError):
        _check_clear_scene_screen_resets_everything(_mutate(anchor, replacement))


def _check_player_is_shown_only_after_pick(source: str) -> None:
    """영상은 장면을 실제로 고른 순간에만 보이고, 화면을 비울 때는 감춘다."""
    tree = _app_source_tree(source)
    assert ("player_box", True) in _set_visibility_calls(_function_def(tree, "pick_scene"))
    cleared = _set_visibility_calls(_function_def(tree, "clear_scene_screen"))
    assert ("player_box", False) in cleared
    assert ("player_box", True) not in cleared


def test_video_player_is_shown_only_after_a_scene_is_picked() -> None:
    _check_player_is_shown_only_after_pick(_app_source_text())


def test_player_visibility_check_catches_a_pick_scene_that_never_shows_the_player() -> None:
    mutated = _mutate("        player_box.set_visibility(True)\n", "")
    with pytest.raises(AssertionError):
        _check_player_is_shown_only_after_pick(mutated)


def test_player_visibility_check_catches_a_player_left_visible_after_clearing() -> None:
    mutated = _mutate(
        "        player_box.set_visibility(False)\n",
        "        player_box.set_visibility(True)\n",
    )
    with pytest.raises(AssertionError):
        _check_player_is_shown_only_after_pick(mutated)


def _check_scene_state_lives_in_scene_work_state(source: str) -> None:
    """장면 상태는 nonlocal 변수로 흩어지지 않고 SceneWorkState 하나가 들고 있다."""
    tree = _app_source_tree(source)
    assert "ui_controller.SceneWorkState" in _call_names(tree)
    scattered = {"found", "rows", "saved_scenes", "selected_index"} & _nonlocal_names(tree)
    assert not scattered, f"장면 상태가 nonlocal로 흩어져 있습니다: {sorted(scattered)}"


def test_app_keeps_scene_state_in_scene_work_state() -> None:
    _check_scene_state_lives_in_scene_work_state(_app_source_text())


def test_scene_state_check_catches_a_missing_scene_work_state() -> None:
    mutated = _mutate("state = ui_controller.SceneWorkState()", "state = None")
    with pytest.raises(AssertionError):
        _check_scene_state_lives_in_scene_work_state(mutated)


def test_scene_state_check_catches_state_scattered_back_into_nonlocals() -> None:
    mutated = _mutate("nonlocal player", "nonlocal player, rows, selected_index")
    with pytest.raises(AssertionError):
        _check_scene_state_lives_in_scene_work_state(mutated)
