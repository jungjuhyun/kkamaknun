"""정확 후보 장면의 앞뒤 문맥을 조회해 구조화된 한국어 번역을 만든다."""

from __future__ import annotations

from dataclasses import dataclass

from nadeshiko import Nadeshiko
from nadeshiko.models import Segment, SegmentContextResponse

from scene_collector.ai import create_structured_response
from scene_collector.config import AppSettings
from scene_collector.database import (
    SceneCollectorDatabase,
    StoredExpression,
    StoredSegment,
    _canonical_json,
    _sha256,
)
from scene_collector.models import SceneTranslation, SceneTranslationBatch

CONTEXT_TAKE = 2
TRANSLATION_BATCH_SIZE = 5
TRANSLATION_INSTRUCTION_VERSION = "scene-translation-v1"

_TRANSLATION_RULES = """당신은 일본어 애니 대사를 한국어 학습 자료로 옮기는 번역가입니다.
아래 장면 JSON의 각 장면을 번역하세요.

규칙:
- 제공된 대사와 문맥 텍스트만 사용하세요. 영상, 표정, 성우의 감정, 화면 상황을 직접 본 것처럼 가정하지 마세요.
- 고유명사나 생략된 주어·목적어가 문맥으로 확정되지 않으면 과도하게 특정하지 마세요.
- direct_meaning: 현재 일본어 대사의 직접적인 뜻. 핵심 의미를 생략하지 말고, 억지 직역문은 피하되 자연번역과 구분될 정도로 원문의 의미 구조를 보존하세요.
- natural_translation: 앞뒤 문맥에서 한국 사람이 실제로 이해하기 쉬운 자연스러운 한국어. 원문에 없는 사실을 만들지 마세요.
- scene_usage: 목표 표현이 이 장면에서 어떤 기능으로 쓰이는지 짧고 실용적으로 설명하세요. 예: 상태 확인, 걱정, 요청, 동의, 체념.
- nadeshiko_english는 참고 자료일 뿐입니다. 그대로 옮기지 마세요.
- null인 필드는 해당 정보가 없다는 뜻입니다.
- 한자 어원, 문법 강의, 감정 분석, 긴 해설을 쓰지 마세요.
- 각 장면의 scene_key를 입력 그대로 반환하고, 모든 장면을 빠짐없이 정확히 한 번씩만 포함하세요."""


@dataclass(frozen=True)
class TranslatedScene:
    """한 장면의 문맥과 저장된 한국어 번역 결과."""

    segment_id: int
    segment_public_id: str
    previous_japanese: str | None
    current_japanese: str
    next_japanese: str | None
    nadeshiko_english: str | None
    translation: SceneTranslation


@dataclass(frozen=True)
class _SceneInput:
    stored: StoredSegment
    previous_japanese: str | None
    next_japanese: str | None
    nadeshiko_english: str | None
    payload: dict[str, object]


def translate_expression_scenes(
    settings: AppSettings,
    expression_id: int,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> tuple[TranslatedScene, ...]:
    """사용자가 선택한 표현의 정확 장면들을 문맥과 함께 한국어로 번역해 저장한다."""
    expression = database.load_expression(expression_id)
    if expression is None:
        raise ValueError("번역할 표현을 찾을 수 없습니다.")
    if not expression.segments:
        return ()

    scenes = [
        _scene_input(
            expression,
            stored,
            nadeshiko_client=nadeshiko_client,
            database=database,
        )
        for stored in expression.segments
    ]

    translated: list[TranslatedScene] = []
    for start in range(0, len(scenes), TRANSLATION_BATCH_SIZE):
        batch = scenes[start : start + TRANSLATION_BATCH_SIZE]
        translated.extend(
            _translate_batch(settings, expression_id, batch, database=database)
        )
    return tuple(translated)


def _translate_batch(
    settings: AppSettings,
    expression_id: int,
    batch: list[_SceneInput],
    *,
    database: SceneCollectorDatabase,
) -> list[TranslatedScene]:
    batch_json = _canonical_json([scene.payload for scene in batch])
    input_hash = _sha256(batch_json)
    prompt = "\n".join((_TRANSLATION_RULES, "", "장면 JSON:", batch_json))

    response = create_structured_response(
        settings,
        prompt=prompt,
        response_model=SceneTranslationBatch,
        cache=database,
        instruction_version=TRANSLATION_INSTRUCTION_VERSION,
    )
    by_scene_key = _validated_scene_mapping(
        [scene.stored.segment.public_id for scene in batch],
        response,
    )

    results: list[TranslatedScene] = []
    for scene in batch:
        translation = by_scene_key[scene.stored.segment.public_id]
        database.save_scene_translation(
            expression_id,
            scene.stored.id,
            direct_meaning=translation.direct_meaning,
            natural_translation=translation.natural_translation,
            scene_usage=translation.scene_usage,
            ai_service=settings.ai.service,
            ai_model=settings.ai.model,
            instruction_version=TRANSLATION_INSTRUCTION_VERSION,
            input_hash=input_hash,
        )
        results.append(
            TranslatedScene(
                segment_id=scene.stored.id,
                segment_public_id=scene.stored.segment.public_id,
                previous_japanese=scene.previous_japanese,
                current_japanese=scene.stored.segment.text_ja.content,
                next_japanese=scene.next_japanese,
                nadeshiko_english=scene.nadeshiko_english,
                translation=translation,
            )
        )
    return results


def _validated_scene_mapping(
    expected_keys: list[str],
    response: SceneTranslationBatch,
) -> dict[str, SceneTranslation]:
    returned_keys = [item.scene_key for item in response.translations]
    duplicates = sorted(
        {key for key in returned_keys if returned_keys.count(key) > 1}
    )
    if duplicates:
        raise ValueError(f"AI 번역이 같은 장면을 여러 번 반환했습니다: {', '.join(duplicates)}")

    expected = set(expected_keys)
    returned = set(returned_keys)
    unknown = sorted(returned - expected)
    if unknown:
        raise ValueError(f"AI 번역이 알 수 없는 장면을 반환했습니다: {', '.join(unknown)}")
    missing = sorted(expected - returned)
    if missing:
        raise ValueError(f"AI 번역에서 장면이 누락됐습니다: {', '.join(missing)}")

    return {item.scene_key: item for item in response.translations}


def _scene_input(
    expression: StoredExpression,
    stored: StoredSegment,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> _SceneInput:
    context = _segment_context(
        stored.segment.public_id,
        nadeshiko_client=nadeshiko_client,
        database=database,
    )
    previous_segment, next_segment = _neighbor_segments(stored.segment, context)
    previous_japanese = previous_segment.text_ja.content if previous_segment else None
    next_japanese = next_segment.text_ja.content if next_segment else None
    nadeshiko_english = _english_reference(stored.segment)

    payload: dict[str, object] = {
        "scene_key": stored.segment.public_id,
        "target_expression": {
            "japanese": expression.candidate.japanese,
            "reading": expression.candidate.reading,
            "meaning_ko": expression.candidate.meaning_ko,
        },
        "previous_japanese": previous_japanese,
        "current_japanese": stored.segment.text_ja.content,
        "next_japanese": next_japanese,
        "nadeshiko_english": nadeshiko_english,
    }
    return _SceneInput(
        stored=stored,
        previous_japanese=previous_japanese,
        next_japanese=next_japanese,
        nadeshiko_english=nadeshiko_english,
        payload=payload,
    )


def _segment_context(
    segment_public_id: str,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> SegmentContextResponse:
    cached = database.get_nadeshiko_context_cache(
        segment_public_id=segment_public_id,
        take=CONTEXT_TAKE,
    )
    if cached is not None:
        return cached

    response = nadeshiko_client.get_segment_context(segment_public_id, take=CONTEXT_TAKE)
    database.put_nadeshiko_context_cache(
        segment_public_id=segment_public_id,
        take=CONTEXT_TAKE,
        response=response,
    )
    return response


def _neighbor_segments(
    current: Segment,
    context: SegmentContextResponse,
) -> tuple[Segment | None, Segment | None]:
    """응답 순서를 믿지 않고 같은 작품·같은 화의 가장 가까운 앞뒤 장면을 고른다."""
    same_episode = [
        segment
        for segment in context.segments
        if segment.media_public_id == current.media_public_id
        and segment.episode == current.episode
        and segment.public_id != current.public_id
    ]
    previous_segment = max(
        (segment for segment in same_episode if segment.position < current.position),
        key=lambda segment: segment.position,
        default=None,
    )
    next_segment = min(
        (segment for segment in same_episode if segment.position > current.position),
        key=lambda segment: segment.position,
        default=None,
    )
    return previous_segment, next_segment


def _english_reference(segment: Segment) -> str | None:
    content = segment.text_en.content.strip()
    if not content:
        return None
    if segment.text_en.is_machine_translated:
        return f"{content} (기계번역)"
    return content
