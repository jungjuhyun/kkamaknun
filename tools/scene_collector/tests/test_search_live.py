import json
import os
from pathlib import Path

import pytest

from scene_collector.config import load_settings
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import search_expressions

INTENTS_PATH = Path(__file__).parent / "fixtures" / "search_live_intents.json"


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"Missing required live-test environment variable: {name}")
    return value


@pytest.mark.search_live
def test_korean_intents_reach_corpus_backed_candidates(tmp_path: Path) -> None:
    _required_environment("GOOGLE_API_KEY")
    _required_environment("NADESHIKO_API_KEY")
    service = _required_environment("SCENE_COLLECTOR_SEARCH_LIVE_SERVICE")
    model = _required_environment("SCENE_COLLECTOR_SEARCH_LIVE_MODEL")
    candidate_count = int(_required_environment("SCENE_COLLECTOR_SEARCH_LIVE_CANDIDATE_COUNT"))
    nadeshiko_take = int(_required_environment("SCENE_COLLECTOR_SEARCH_LIVE_NADESHIKO_TAKE"))

    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {json.dumps(str(work_data_dir))}",
                "",
                "[ai]",
                f"service = {json.dumps(service)}",
                f"model = {json.dumps(model)}",
                "",
                "[search]",
                f"candidate_count = {candidate_count}",
                f"nadeshiko_take = {nadeshiko_take}",
                "",
            )
        ),
        encoding="utf-8",
    )
    settings = load_settings(settings_file)
    intents = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    if len(intents) != 10:
        pytest.fail("search live fixture must contain exactly 10 intents")

    client = create_nadeshiko_client(settings)
    evaluations: list[dict[str, object]] = []
    try:
        for intent in intents:
            result = search_expressions(settings, intent, nadeshiko_client=client)
            searches = []
            for item in result.candidate_searches:
                first_segment = item.response.segments[0] if item.response.segments else None
                searches.append(
                    {
                        **item.candidate.model_dump(by_alias=True),
                        "has_results": item.has_results,
                        "first_japanese": (
                            first_segment.text_ja.content if first_segment is not None else None
                        ),
                        "first_english": (
                            first_segment.text_en.content if first_segment is not None else None
                        ),
                        "fetched_count": len(item.response.segments),
                        "has_more": item.response.pagination.has_more,
                    }
                )
            evaluations.append(
                {
                    "korean_intent": result.korean_intent,
                    "ai_candidates": [
                        candidate.model_dump(by_alias=True)
                        for candidate in result.generated_candidates
                    ],
                    "searches": searches,
                    "corpus_backed_count": len(result.corpus_backed_candidates),
                }
            )
    finally:
        client.close()

    report = {
        "service": settings.ai.service,
        "model": settings.ai.model,
        "ai_generation_success_count": len(evaluations),
        "inputs_with_corpus_backed_candidates": sum(
            evaluation["corpus_backed_count"] > 0 for evaluation in evaluations
        ),
        "total_ai_candidates": sum(
            len(evaluation["ai_candidates"]) for evaluation in evaluations
        ),
        "total_corpus_backed_candidates": sum(
            evaluation["corpus_backed_count"] for evaluation in evaluations
        ),
        "evaluations": evaluations,
    }
    report_path_value = os.environ.get("SCENE_COLLECTOR_SEARCH_LIVE_REPORT")
    if report_path_value:
        Path(report_path_value).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    assert report["ai_generation_success_count"] == 10
