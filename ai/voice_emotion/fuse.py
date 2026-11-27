# fuse.py
# 글 감정 결과(analyze_text 양식)에 목소리 확률을 섞습니다: 최종 = (1−w)·글 + w·목소리.
# 반올림·합 1 맞추기와 확신도는 글 감정(emotion_mapper)과 같은 함수를 씁니다.
from ai.emotion.emotion_mapper import EMOTIONS, fix_probs_sum, get_confidence

__all__ = ["EMOTIONS", "fuse"]


def fuse(result: dict, voice_probs: dict, w: float) -> dict:
    """analyze_text 결과와 같은 키의 새 dict. 입력은 바꾸지 않습니다."""
    mixed = {k: (1 - w) * result["probs"][k] + w * voice_probs[k] for k in EMOTIONS}
    emotion = max(mixed, key=mixed.get)  # 반올림 전 값 기준 (predict_emotion과 같음)
    probs = fix_probs_sum(mixed, emotion)
    return {**result, "probs": probs, "emotion": emotion, "confidence": get_confidence(probs[emotion])}
