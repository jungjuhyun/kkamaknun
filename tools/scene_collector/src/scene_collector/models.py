"""장면 수집기에서 검증해 사용하는 제품 자료형."""

from pydantic import BaseModel, ConfigDict, Field


class ExpressionCandidate(BaseModel):
    """한국어 의도에서 생성된 일본어 표현 후보."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    japanese: str = Field(min_length=1, description="자연스러운 일본어 회화 표현")
    reading: str = Field(min_length=1, description="표현 전체의 가나 읽기")
    meaning_ko: str = Field(min_length=1, description="후보가 표현하는 간결한 한국어 의미")
    register_: str = Field(
        alias="register",
        min_length=1,
        description="말투 또는 격식 수준의 짧은 설명",
    )

    @property
    def register(self) -> str:
        return self.register_


class ExpressionCandidates(BaseModel):
    """Instructor 구조화 출력으로 받는 일본어 표현 후보 목록."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[ExpressionCandidate] = Field(min_length=3, max_length=5)


class SceneTranslation(BaseModel):
    """한 장면에 대한 구조화된 한국어 번역 결과."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scene_key: str = Field(min_length=1, description="입력에서 받은 장면 식별자를 그대로 반환")
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


class SceneTranslationBatch(BaseModel):
    """여러 장면을 한 요청으로 번역한 구조화 출력."""

    model_config = ConfigDict(extra="forbid")

    translations: list[SceneTranslation] = Field(min_length=1)
