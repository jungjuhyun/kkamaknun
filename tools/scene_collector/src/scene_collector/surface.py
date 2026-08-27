"""일본어 원문에서 같은 표면형의 표현만 보수적으로 찾는다."""

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_TERMINAL_PUNCTUATION = "?!。.．"
_SHORT_SURFACE_LENGTH = 2


@dataclass(frozen=True)
class _NormalizedSource:
    text: str
    whitespace_boundaries: frozenset[int]


@dataclass(frozen=True)
class _NormalizedTokens:
    spans: frozenset[tuple[int, int]]
    starts: frozenset[int]


def matches_surface(
    source_text: str,
    primary_surface: str,
    *,
    allowed_surfaces: Iterable[str] = (),
    token_spans: Iterable[tuple[int, int]] | None = None,
) -> bool:
    """대표 표기나 명시적 허용 표기가 원문에 같은 표면형으로 있는지 확인한다.

    NFKC 폭 차이와 공백, 표현 끝 문장부호만 비교에서 완화한다. 내부
    문장부호와 일본어 활용은 그대로 보존한다. Nadeshiko top-level token
    위치가 있으면 앞뒤 표현 경계를 확인하고, 형태소 정보가 없는 짧은
    표면형은 복합어 내부 일치를 피하기 위해 보수적으로 판정한다.
    """
    source = _normalize_source(source_text)
    normalized_tokens = _normalize_token_spans(source_text, token_spans)
    surfaces = (primary_surface, *allowed_surfaces)
    normalized_surfaces: list[str] = []

    for surface in surfaces:
        normalized = _normalize_surface(surface)
        if not normalized:
            raise ValueError("표면형에는 문장부호가 아닌 문자가 있어야 합니다.")
        if normalized not in normalized_surfaces:
            normalized_surfaces.append(normalized)

    return any(
        _contains_surface(source, surface, normalized_tokens) for surface in normalized_surfaces
    )


def _normalize_source(text: str) -> _NormalizedSource:
    normalized = unicodedata.normalize("NFKC", text)
    compact: list[str] = []
    whitespace_boundaries: set[int] = set()

    for character in normalized:
        if character.isspace():
            whitespace_boundaries.add(len(compact))
            continue
        compact.append(character)

    return _NormalizedSource(
        text="".join(compact),
        whitespace_boundaries=frozenset(whitespace_boundaries),
    )


def _normalize_surface(text: str) -> str:
    compact = "".join(
        character for character in unicodedata.normalize("NFKC", text) if not character.isspace()
    )
    return compact.rstrip(_TERMINAL_PUNCTUATION)


def _normalize_token_spans(
    source_text: str,
    token_spans: Iterable[tuple[int, int]] | None,
) -> _NormalizedTokens | None:
    if token_spans is None:
        return None

    normalized_spans: set[tuple[int, int]] = set()
    for begin, end in token_spans:
        if not 0 <= begin < end <= len(source_text):
            continue
        normalized_begin = len(_normalize_source(source_text[:begin]).text)
        normalized_end = len(_normalize_source(source_text[:end]).text)
        if normalized_begin < normalized_end:
            normalized_spans.add((normalized_begin, normalized_end))

    if not normalized_spans:
        return None

    return _NormalizedTokens(
        spans=frozenset(normalized_spans),
        starts=frozenset(begin for begin, _ in normalized_spans),
    )


def _contains_surface(
    source: _NormalizedSource,
    surface: str,
    normalized_tokens: _NormalizedTokens | None,
) -> bool:
    start = 0
    while True:
        index = source.text.find(surface, start)
        if index < 0:
            return False

        end = index + len(surface)
        if _has_right_boundary(
            source.text,
            index,
            end,
            normalized_tokens,
        ) and _has_left_boundary(
            source,
            index,
            surface,
            normalized_tokens,
        ):
            return True
        start = index + 1


def _has_right_boundary(
    source: str,
    start: int,
    end: int,
    normalized_tokens: _NormalizedTokens | None,
) -> bool:
    if end == len(source) or _is_boundary_character(source[end]):
        return True
    return normalized_tokens is not None and (start, end) in normalized_tokens.spans


def _has_left_boundary(
    source: _NormalizedSource,
    start: int,
    surface: str,
    normalized_tokens: _NormalizedTokens | None,
) -> bool:
    if start == 0:
        return True
    if _is_boundary_character(source.text[start - 1]):
        return True
    if normalized_tokens is not None:
        return start in normalized_tokens.starts
    if start in source.whitespace_boundaries:
        return True
    return len(surface) > _SHORT_SURFACE_LENGTH


def _is_boundary_character(character: str) -> bool:
    return unicodedata.category(character)[0] in {"P", "S"}
