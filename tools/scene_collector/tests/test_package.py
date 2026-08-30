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
        "clear_scene_screen()\n        token = state.start_relation(chosen)",
        "token = state.start_relation(chosen)",
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


# ----------------------------------------------------------------------
# 늦게 도착한 조회 결과가 새 화면을 덮지 않는다
# ----------------------------------------------------------------------


def _check_late_results_are_guarded(source: str) -> None:
    """await 뒤에 결과를 반영하는 함수는 그 표가 아직 현재인지 먼저 확인한다."""
    tree = _app_source_tree(source)
    for name in ("select_relation", "refresh_rows"):
        calls = _call_names(_function_def(tree, name))
        assert "state.is_current" in calls, name


def test_select_relation_and_refresh_rows_drop_stale_results() -> None:
    _check_late_results_are_guarded(_app_source_text())


def test_late_result_check_catches_a_missing_guard_in_refresh_rows() -> None:
    """refresh_rows 의 단 하나뿐인 보호를 지우면 검사가 실패해야 한다."""
    mutated = _mutate(
        "        if not state.is_current(token):\n            return\n        state.rows = rows",
        "        state.rows = rows",
    )
    with pytest.raises(AssertionError):
        _check_late_results_are_guarded(mutated)


def test_late_result_check_catches_a_renamed_guard() -> None:
    """보호 장치의 이름만 바꿔 실제로는 확인하지 않게 만들어도 잡아야 한다."""
    source = _app_source_text()
    assert source.count("state.is_current(") >= 2
    with pytest.raises(AssertionError):
        _check_late_results_are_guarded(
            source.replace("state.is_current(", "state.was_current(")
        )


def _check_expression_list_is_reset_on_a_new_meaning(source: str) -> None:
    """의미를 새로 조회하면 이전 의미의 표현 버튼이 남지 않는다.

    조회를 기다리는 동안 옛 표현 버튼이 눌리면 새 의미와 옛 표현이 섞인다.
    """
    tree = _app_source_tree(source)
    lookup = _call_names(_function_def(tree, "do_lookup"))
    assert "clear_scene_screen" in lookup
    assert "render_expressions" in lookup
    # 표현 더 찾기로 다른 의미를 조회한 경우에도 이전 장면 화면이 남으면 안 된다.
    generate = _call_names(_function_def(tree, "do_generate"))
    assert "clear_scene_screen" in generate
    assert "normalize_korean_meaning" in generate


def test_a_new_meaning_resets_the_expression_list_and_scene_screen() -> None:
    _check_expression_list_is_reset_on_a_new_meaning(_app_source_text())


def test_expression_reset_check_catches_a_generate_that_never_clears() -> None:
    mutated = _mutate(
        "            screen = None\n            clear_scene_screen()\n            render_expressions()",
        "            screen = None",
    )
    with pytest.raises(AssertionError):
        _check_expression_list_is_reset_on_a_new_meaning(mutated)


# ----------------------------------------------------------------------
# UAT 수정: Enter 검색 · 카드 단순화 · 고정 메뉴 · 설정 편집
# ----------------------------------------------------------------------


def _attribute_names(node: ast.AST) -> set[str]:
    """노드 안에서 읽는 속성 이름을 모은다."""
    return {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)}


def _event_bindings(tree: ast.Module, target: str) -> dict[str, ast.Call]:
    """`<target>.on("<type>", ...)` 호출을 이벤트 이름으로 모은다."""
    bindings: dict[str, ast.Call] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "on"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == target
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            bindings[node.args[0].value] = node
    return bindings


def _module_constant(tree: ast.Module, name: str) -> str:
    """모듈 수준 문자열 상수 하나를 읽는다."""
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise AssertionError(f"모듈 상수 {name}을(를) 찾지 못했습니다.")


def _with_ui_blocks(tree: ast.Module, widget: str) -> list[ast.With]:
    """`with ui.<widget>(...)` 블록을 모은다. 메서드를 이어 붙여도 찾는다."""
    blocks: list[ast.With] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            if f"ui.{widget}" in _call_names(ast.Expression(body=item.context_expr)):
                blocks.append(node)
                break
    return blocks


def _check_enter_runs_the_same_lookup(source: str) -> None:
    """Enter와 버튼이 같은 do_lookup 하나를 부르고, 중복 실행을 막는다."""
    tree = _app_source_tree(source)
    bindings = _event_bindings(tree, "meaning_input")
    assert "keydown.enter" in bindings
    enter = bindings["keydown.enter"]
    assert "do_lookup" in _call_names(enter)
    # 한국어 IME 조합 확정 Enter를 client에서 걸러야 한다.
    assert "js_handler" in {keyword.arg for keyword in enter.keywords}
    assert "isComposing" in _module_constant(tree, "_ENTER_WITHOUT_IME")
    # 버튼도 그대로 남아 같은 함수를 부른다.
    assert "표현 찾기" in _ui_labels(tree, "button")
    lookup = _call_names(_function_def(tree, "do_lookup"))
    assert "lookup_guard.try_begin" in lookup
    assert "lookup_guard.finish" in lookup
    # 빈 입력 경고는 그대로 둔다.
    assert "ui.notify" in lookup


def test_enter_and_the_button_share_one_lookup() -> None:
    _check_enter_runs_the_same_lookup(_app_source_text())


@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        ('meaning_input.on(\n                "keydown.enter"', "meaning_input.on(\n                \"blur\""),
        ("if (!event.isComposing && event.keyCode !== 229) emit();", "emit();"),
        (
            "        if not lookup_guard.try_begin():",
            "        if False:",
        ),
    ],
)
def test_enter_check_catches_a_broken_binding(anchor: str, replacement: str) -> None:
    with pytest.raises(AssertionError):
        _check_enter_runs_the_same_lookup(_mutate(anchor, replacement))


def _check_expression_card_is_simplified(source: str) -> None:
    """카드에는 일본어와 한글 독음, 말투만 둔다."""
    tree = _app_source_tree(source)
    used = _attribute_names(tree)
    # 히라가나 읽기와 "이 의미에서의 뜻"은 화면에 직접 내지 않는다.
    assert "reading" not in used
    assert "meaning_ko" not in used
    card = _function_def(tree, "render_expressions")
    assert "ui_controller.expression_line" in _call_names(card)
    assert "register_text" in _attribute_names(card)


def test_expression_card_shows_a_korean_reading_only() -> None:
    _check_expression_card_is_simplified(_app_source_text())


@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        (
            "ui.label(ui_controller.expression_line(item)).style",
            'ui.label(f"{item.japanese} ({item.reading})").style',
        ),
        (
            '                    ui.label(f"말투: {item.register_text}")',
            '                    ui.label(f"말투: {item.register_text}")\n'
            '                    ui.label(f"뜻: {item.meaning_ko}")',
        ),
    ],
)
def test_expression_card_check_catches_a_restored_line(anchor: str, replacement: str) -> None:
    with pytest.raises(AssertionError):
        _check_expression_card_is_simplified(_mutate(anchor, replacement))


def _check_curated_hides_internal_classification(source: str) -> None:
    """추천 목록에 tier·근거 등급 같은 내부 분류가 노출되지 않는다."""
    tree = _app_source_tree(source)
    whole = _attribute_names(tree)
    assert "tier" not in whole
    assert "popularity_evidence_grade" not in whole
    assert "note" not in whole
    node = _function_def(tree, "render_curated")
    names = _attribute_names(node)
    assert "korean_title" in names
    assert "status_label" in names
    # A군/B군 필터는 계속 살아 있어야 한다.
    assert "group" in names
    # 사용자가 몰라도 되는 내부 용어를 안내 문구에 쓰지 않는다.
    assert not any("entry" in label for label in _ui_labels(tree, "label"))


def test_curated_list_hides_internal_classification() -> None:
    _check_curated_hides_internal_classification(_app_source_text())


@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        (
            "                    ui.label(item.korean_title)",
            '                    ui.label(f"[{item.group}{item.tier}] {item.korean_title}")',
        ),
        (
            '"작품을 체크하면 현재 지원되는 연결 항목이 함께 검색 대상이 됩니다."',
            '"프랜차이즈 하나를 체크하면 연결된 entry가 함께 활성화됩니다."',
        ),
        (
            # 두 갈래를 함께 지워야 group 참조가 실제로 사라진다.
            '                or (selected == "A군" and view.item.group == "A")\n'
            '                or (selected == "B군" and view.item.group == "B")\n',
            "",
        ),
    ],
)
def test_curated_check_catches_restored_internals(anchor: str, replacement: str) -> None:
    with pytest.raises(AssertionError):
        _check_curated_hides_internal_classification(_mutate(anchor, replacement))


def _check_tabs_live_in_the_fixed_header(source: str) -> None:
    """제목과 탭이 함께 고정 헤더 안에 있고 본문(패널)만 스크롤된다."""
    tree = _app_source_tree(source)
    headers = _with_ui_blocks(tree, "header")
    assert len(headers) == 1
    header_calls = _call_names(headers[0])
    assert "ui.tabs" in header_calls
    # 본문에는 탭 생성이 남아 있지 않다(스크롤하면 사라지던 옛 배치).
    assert _call_names(tree).count("ui.tabs") == header_calls.count("ui.tabs")
    # 탭 내용은 헤더 밖에 있어 계속 스크롤된다.
    assert "ui.tab_panels" not in header_calls
    assert "ui.tab_panels" in _call_names(tree)


def test_title_and_tabs_are_both_in_the_fixed_header() -> None:
    _check_tabs_live_in_the_fixed_header(_app_source_text())


@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        (
            "    with ui.header().props(f\"height-hint={_HEADER_HEIGHT_HINT}\"):",
            '    with ui.column().classes("items-center"):',
        ),
        (
            '    with ui.tab_panels(tabs, value=search_tab).classes("w-full"):',
            "    ui.tabs()\n"
            '    with ui.tab_panels(tabs, value=search_tab).classes("w-full"):',
        ),
    ],
)
def test_fixed_header_check_catches_tabs_outside_it(anchor: str, replacement: str) -> None:
    with pytest.raises(AssertionError):
        _check_tabs_live_in_the_fixed_header(_mutate(anchor, replacement))


def _check_settings_tab_edits_known_keys(source: str) -> None:
    """설정 탭에서 숫자 두 개를 바꿔 저장할 수 있다."""
    tree = _app_source_tree(source)
    numbers = _ui_labels(tree, "number")
    assert "표현 생성 상한" in numbers
    # 찾은 장면 수를 자르는 설정은 없다.
    assert "표시할 장면 수" not in numbers
    assert "설정 저장" in _ui_labels(tree, "button")

    save = _function_def(tree, "do_save_settings")
    calls = _call_names(save)
    # 저장 책임은 config에 있고 화면은 부르기만 한다.
    assert "save_search_settings" in calls
    assert "ui_controller.parse_setting_number" in calls
    # 화면이 직접 파일을 쓰지 않는다.
    assert "open" not in calls
    assert "write_text" not in calls
    # 작업 데이터 위치와 API 키는 편집 대상이 아니다.
    assert "작업 데이터 위치" not in numbers
    assert not any("API 키" in label for label in _ui_labels(tree, "input"))


def test_settings_tab_can_save_the_generation_limit() -> None:
    _check_settings_tab_edits_known_keys(_app_source_text())


@pytest.mark.parametrize(
    ("anchor", "replacement"),
    [
        ("                lambda: save_search_settings(", "                lambda: load_settings("),
    ],
)
def test_settings_tab_check_catches_a_broken_save(anchor: str, replacement: str) -> None:
    with pytest.raises(AssertionError):
        _check_settings_tab_edits_known_keys(_mutate(anchor, replacement))
