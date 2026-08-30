"""장면 수집기에서 검증해 사용하는 제품 자료형."""

from pydantic import BaseModel, ConfigDict, Field

EXPRESSION_GENERATION_HARD_LIMIT = 20


class ExpressionCandidate(BaseModel):
    """한국어 의미에 대응하는 일본어 표현 하나.

    meaning_ko와 register는 이 한국어 의미에서의 설명이며, 저장할 때는
    표현 자체가 아니라 의미↔표현 관계에 들어간다.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    japanese: str = Field(min_length=1, description="자연스러운 일본어 회화 표현")
    reading: str = Field(min_length=1, description="표현 전체의 가나 읽기")
    meaning_ko: str = Field(min_length=1, description="이 한국어 의미에서의 간결한 뜻")
    register_: str = Field(
        alias="register",
        min_length=1,
        description="말투 또는 격식 수준의 짧은 설명",
    )

    @property
    def register(self) -> str:
        return self.register_


class GeneratedExpressions(BaseModel):
    """한국어 의미 하나에 대해 AI가 생성한 일본어 표현 목록.

    자연스러운 표현만 담고 상한까지 억지로 채우지 않으므로 개수는 유연하다.
    """

    model_config = ConfigDict(extra="forbid")

    expressions: list[ExpressionCandidate] = Field(
        min_length=1, max_length=EXPRESSION_GENERATION_HARD_LIMIT
    )


class SceneTranslation(BaseModel):
    """사용자가 요청한 장면 하나에 대한 구조화된 한국어 번역 결과."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    direct_meaning: str = Field(
        min_length=1,
        description="현재 일본어 대사의 직접적인 뜻",
    )
    natural_translation: str = Field(
        min_length=1,
        description="앞뒤 문맥에서 자연스러운 한국어 번역",
    )
    scene_usage: str = Field(
        min_length=1,
        description="목표 표현이 이 장면에서 쓰이는 기능의 짧은 설명",
    )
