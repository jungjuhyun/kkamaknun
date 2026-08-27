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
