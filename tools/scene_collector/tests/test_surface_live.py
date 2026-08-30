import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from nadeshiko import Nadeshiko
from nadeshiko.models import SearchQuery, SearchResponse, Segment

from scene_collector.config import load_settings
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.surface import matches_surface

TARGETS = (
    "悪い",
    "ほんとそれ",
    "ん？なんて？",
    "今、何してるんですか？",
    "大丈夫ですか？",
    "もう一回言って。",
)
FALSE_POSITIVE_TARGETS = TARGETS[:4]
LIVE_POSITIVE_TARGETS = ("大丈夫ですか？", "もう一回言って。")
DEFAULT_TAKE = 20


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"Missing required live-test environment variable: {name}")
    return value


def _take() -> int:
    raw_value = os.environ.get("SCENE_COLLECTOR_SURFACE_LIVE_TAKE", str(DEFAULT_TAKE))
    try:
        value = int(raw_value)
    except ValueError:
        pytest.fail("SCENE_COLLECTOR_SURFACE_LIVE_TAKE must be an integer")
    if not 1 <= value <= 100:
        pytest.fail("SCENE_COLLECTOR_SURFACE_LIVE_TAKE must be between 1 and 100")
    return value


@pytest.fixture(scope="module")
def live_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Nadeshiko]:
    _required_environment("NADESHIKO_API_KEY")
    config_dir = tmp_path_factory.mktemp("surface-live")
    settings_file = config_dir / "settings.toml"
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {json.dumps(str(config_dir))}",
                "",
                "[ai]",
                'service = "unused-in-task-5"',
                'model = "unused-in-task-5"',
                "",
                "[search]",
                "expression_generation_limit = 5",
                f"nadeshiko_take = {min(_take(), 20)}",
                "",
            )
        ),
        encoding="utf-8",
    )
    client = create_nadeshiko_client(load_settings(settings_file))
    yield client
    client.close()


def _first_text(segments: list[Segment] | tuple[Segment, ...]) -> str | None:
    return segments[0].text_ja.content if segments else None


def _matches_segment(segment: Segment, target: str) -> bool:
    tokens = segment.text_ja.tokens
    token_spans = (
        tuple(
            (begin, end)
            for token in tokens
            if isinstance((begin := getattr(token, "b", None)), int)
            and isinstance((end := getattr(token, "e", None)), int)
        )
        if isinstance(tokens, list)
        else None
    )
    return matches_surface(
        segment.text_ja.content,
        target,
        token_spans=token_spans,
    )


def _removed_example(response: SearchResponse, target: str) -> str | None:
    return next(
        (
            segment.text_ja.content
            for segment in response.segments
            if not _matches_segment(segment, target)
        ),
        None,
    )


def _normal_only_removed_example(
    normal: SearchResponse,
    exact: SearchResponse,
    target: str,
) -> str | None:
    exact_segment_ids = {segment.public_id for segment in exact.segments}
    return next(
        (
            segment.text_ja.content
            for segment in normal.segments
            if segment.public_id not in exact_segment_ids and not _matches_segment(segment, target)
        ),
        None,
    )


def _response_summary(response: SearchResponse) -> dict[str, object]:
    return {
        "fetched_count": len(response.segments),
        "estimated_total_hits": response.pagination.estimated_total_hits,
        "estimated_total_hits_relation": response.pagination.estimated_total_hits_relation,
        "tokenized_count": sum(segment.text_ja.tokens is not None for segment in response.segments),
    }


@pytest.mark.surface_live
def test_exact_match_and_local_surface_filter(live_client: Nadeshiko) -> None:
    take = _take()
    evaluations: list[dict[str, object]] = []

    for target in TARGETS:
        normal = live_client.search(query=SearchQuery(search=target), take=take)
        exact = live_client.search(
            query=SearchQuery(search=target, exact_match=True),
            take=take,
        )
        normal_local_segments = tuple(
            segment for segment in normal.segments if _matches_segment(segment, target)
        )
        exact_local_segments = tuple(
            segment for segment in exact.segments if _matches_segment(segment, target)
        )
        final_segments = normal_local_segments or exact_local_segments
        evaluations.append(
            {
                "target": target,
                "normal": _response_summary(normal),
                "exact_match": _response_summary(exact),
                "normal_local_filtered_count": len(normal_local_segments),
                "exact_local_filtered_count": len(exact_local_segments),
                "selected_search": "normal" if normal_local_segments else "exact_match",
                "local_filtered_count": len(final_segments),
                "normal_removed_example": _removed_example(normal, target),
                "normal_only_removed_example": _normal_only_removed_example(
                    normal,
                    exact,
                    target,
                ),
                "exact_removed_example": _removed_example(exact, target),
                "normal_accepted_example": _first_text(normal_local_segments),
                "exact_accepted_example": _first_text(exact_local_segments),
                "accepted_example": _first_text(final_segments),
            }
        )

    report_path_value = os.environ.get("SCENE_COLLECTOR_SURFACE_LIVE_REPORT")
    if report_path_value:
        Path(report_path_value).write_text(
            json.dumps(evaluations, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    by_target = {evaluation["target"]: evaluation for evaluation in evaluations}
    assert all(evaluation["normal"]["fetched_count"] > 0 for evaluation in evaluations)
    assert all(evaluation["exact_match"]["fetched_count"] > 0 for evaluation in evaluations)
    assert all(
        by_target[target]["exact_removed_example"] is not None for target in FALSE_POSITIVE_TARGETS
    )
    assert all(
        by_target[target]["local_filtered_count"] > 0
        and by_target[target]["accepted_example"] is not None
        for target in LIVE_POSITIVE_TARGETS
    )
    assert all(
        (evaluation["local_filtered_count"] > 0) == (evaluation["accepted_example"] is not None)
        for evaluation in evaluations
    )
