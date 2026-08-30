import ast
from pathlib import Path

import scene_collector


def test_package_is_importable() -> None:
    assert scene_collector.__name__ == "scene_collector"


def _app_source_tree() -> ast.Module:
    app_file = Path(scene_collector.__file__).parent / "app.py"
    return ast.parse(app_file.read_text(encoding="utf-8"))


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
