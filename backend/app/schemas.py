from typing import Literal

from pydantic import BaseModel, Field, model_validator

Emotion = Literal["좋음", "무난함", "가라앉음", "예민함"]
Confidence = Literal["높음", "중간", "낮음"]
EMOTIONS = ("좋음", "무난함", "가라앉음", "예민함")


class RecordCreate(BaseModel):
    # 사진만 기록하는 경우에도 확장할 수 있도록 빈 문자를 허용합니다.
    text: str = Field(default="", max_length=2000)


class EmotionResult(BaseModel):
    """상현 -> 건호: 전달받은 JSON의 키를 그대로 사용합니다."""
    record_id: int = Field(gt=0)
    text: str = Field(max_length=2000)
    probs: dict[str, float]
    emotion: Emotion
    confidence: Confidence

    @model_validator(mode="after")
    def check_probabilities(self):
        if set(self.probs) != set(EMOTIONS):
            raise ValueError(f"probs에는 반드시 {EMOTIONS} 네 감정이 필요합니다")
        if not all(0.0 <= value <= 1.0 for value in self.probs.values()):
            raise ValueError("감정별 확률은 0~1이어야 합니다")
        if abs(sum(self.probs.values()) - 1.0) > 0.02:
            raise ValueError("감정별 확률의 합은 1에 가까워야 합니다")
        return self


class RecommendationRequest(BaseModel):
    record_id: int = Field(gt=0)
    # 예측 emotion이 아닌 '사용자가 최종 확인한 감정'을 받아야 합니다.
    confirmed_emotion: Emotion


class Song(BaseModel):
    song_id: str
    brightness: float = Field(ge=0, le=1)
    energy: float = Field(ge=0, le=1)
    step: str


class RecommendationResponse(BaseModel):
    songs: list[Song] = Field(min_length=3, max_length=3)


class SongFeedbackUpdate(BaseModel):
    """추천곡 1곡에 대한 반응. 보낸 항목만 바꿉니다(보내지 않은 항목은 그대로)."""
    is_liked: bool | None = None
    is_skipped: bool | None = None
    is_completed: bool | None = None

    @model_validator(mode="after")
    def check_not_empty(self):
        if self.is_liked is None and self.is_skipped is None and self.is_completed is None:
            raise ValueError("is_liked, is_skipped, is_completed 중 하나 이상을 보내야 합니다")
        return self


class SongFeedback(BaseModel):
    record_id: int
    recommend_order: int = Field(ge=1, le=3)
    song_id: str
    is_liked: bool
    is_skipped: bool
    is_completed: bool
    is_engraved: bool
