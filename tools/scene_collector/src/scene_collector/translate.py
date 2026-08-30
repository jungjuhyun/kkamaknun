"""사용자가 요청한 장면 하나의 앞뒤 문맥을 조회해 한국어 번역을 만든다.

문맥 응답은 즉석에서 쓰고 저장·캐시하지 않는다. 번역 결과는 캐시가 아니라
사용자 작업물이므로 해당 작업 장면(work_scenes)에 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from nadeshiko import Nadeshiko
from nadeshiko.models import Segment, SegmentContextResponse

from scene_collector.ai import create_structured_response
from scene_collector.config import AppSettings
from scene_collector.database import SceneCollectorDatabase, StoredMeaningExpression
from scene_collector.models import SceneTranslation

CONTEXT_TAKE = 2
TRANSLATION_INSTRUCTION_VERSION = "scene-translation-v2"

_TRANSLATION_RULES = """당신은 일본어 애니 대사를 한국어 학습 자료로 옮기는 번역가입니다.
아래 장면 하나를 번역하세요.

규칙:
- 제공된 대사와 문맥 텍스트만 사용하세요. 영상, 표정, 성우의 감정, 화면 상황을 직접 본 것처럼 가정하지 마세요.
- 고유명사나 생략된 주어·목적어가 문맥으로 확정되지 않으면 과도하게 특정하지 마세요.
- direct_meaning: 현재 일본어 대사의 직접적인 뜻. 핵심 의미를 생략하지 말고, 억지 직역문은 피하되 자연번역과 구분될 정도로 원문의 의미 구조를 보존하세요.
- natural_translation: 앞뒤 문맥에서 한국 사람이 실제로 이해하기 쉬운 자연스러운 한국어. 원문에 없는 사실을 만들지 마세요.
- scene_usage: 목표 표현이 이 장면에서 어떤 기능으로 쓰이는지 짧고 실용적으로 설명하세요. 예: 상태 확인, 걱정, 요청, 동의, 체념.
- nadeshiko_english는 참고 자료일 뿐입니다. 그대로 옮기지 마세요.
- 값이 없는 항목은 해당 정보가 없다는 뜻입니다.
- 한자 어원, 문법 강의, 감정 분석, 긴 해설을 쓰지 마세요."""


@dataclass(frozen=True)
class TranslatedScene:
    """한 장면의 문맥과 저장된 한국어 번역 결과."""

    work_scene_id: int
    segment_public_id: str
    previous_japanese: str | None
    current_japanese: str
    next_japanese: str | None
    nadeshiko_english: str | None
    translation: SceneTranslation


def translate_work_scene(
    settings: AppSettings,
    *,
    relation: StoredMeaningExpression,
    segment: Segment,
    work_scene_id: int,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> TranslatedScene:
    """사용자가 요청한 장면 하나만 문맥 조회 후 번역하고 작업물로 저장한다."""
    context = nadeshiko_client.get_segment_context(segment.public_id, take=CONTEXT_TAKE)
    previous_segment, next_segment = _neighbor_segments(segment, context)
    previous_japanese = previous_segment.text_ja.content if previous_segment else None
    next_japanese = next_segment.text_ja.content if next_segment else None
    nadeshiko_english = _english_reference(segment)

    translation = create_structured_response(
        settings,
        prompt=_scene_prompt(
            relation=relation,
            previous_japanese=previous_japanese,
            current_japanese=segment.text_ja.content,
            next_japanese=next_japanese,
            nadeshiko_english=nadeshiko_english,
        ),
        response_model=SceneTranslation,
    )

    database.save_work_scene_translation(
        work_scene_id,
        direct_meaning=translation.direct_meaning,
        natural_translation=translation.natural_translation,
        scene_usage=translation.scene_usage,
        ai_service=settings.ai.service,
        ai_model=settings.ai.model,
        instruction_version=TRANSLATION_INSTRUCTION_VERSION,
    )
    return TranslatedScene(
        work_scene_id=work_scene_id,
        segment_public_id=segment.public_id,
        previous_japanese=previous_japanese,
        current_japanese=segment.text_ja.content,
        next_japanese=next_japanese,
        nadeshiko_english=nadeshiko_english,
        translation=translation,
    )


def _scene_prompt(
    *,
    relation: StoredMeaningExpression,
    previous_japanese: str | None,
    current_japanese: str,
    next_japanese: str | None,
    nadeshiko_english: str | None,
) -> str:
    lines = [
        _TRANSLATION_RULES,
        "",
        "장면 정보:",
        f"- 목표 표현: {relation.japanese} ({relation.reading})",
        f"- 목표 표현의 한국어 의미: {relation.meaning_ko}",
        f"- 앞 대사: {previous_japanese or '(없음)'}",
        f"- 현재 일본어 대사: {current_japanese}",
        f"- 뒤 대사: {next_japanese or '(없음)'}",
        f"- nadeshiko_english: {nadeshiko_english or '(없음)'}",
    ]
    return "\n".join(lines)


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
