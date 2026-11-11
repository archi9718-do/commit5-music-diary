# service.py
# MoodWave 감정 인식의 "입구(창구)" 파일입니다.
# 건호 서버는 이 파일의 analyze_text()와 warm_up()만 부릅니다.
# 3주차에 안쪽 모델을 바꿔도 이 두 함수의 이름과 결과 양식은 그대로 둡니다.
import json
import time

if __package__:
    # 서버에서 ai.emotion.service로 불러올 때 (패키지 방식)
    from .emotion_mapper import EMOTIONS, get_model_dir, load_model, predict_emotion
else:
    # 이 폴더에서 python service.py로 직접 실행할 때
    from emotion_mapper import EMOTIONS, get_model_dir, load_model, predict_emotion

MAX_TEXT_LEN = 2000  # 서버 schemas.py의 text 최대 길이와 같게 맞춤


def warm_up() -> None:
    """서버가 켜질 때 한 번 불러, 모델을 미리 읽고 GPU를 데워 둡니다."""
    load_model()
    predict_emotion("준비 운동")  # 첫 예측만 느리므로 미리 한 번 돌려 둠


def analyze_text(text: str, record_id=None) -> dict:
    """글 한 줄을 받아 감정 결과 양식(dict)을 돌려줍니다.

    결과 예: {"record_id": 1, "text": "...", "probs": {...4종...},
             "emotion": "가라앉음", "confidence": "높음"}
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("감정을 분석할 글이 비어 있습니다.")
    if len(text) > MAX_TEXT_LEN:
        raise ValueError(f"글은 {MAX_TEXT_LEN}자 이하여야 합니다.")

    result = predict_emotion(text, record_id)

    # 결과 양식 점검: 서버가 거절하기 전에 여기서 먼저 잡아냄
    probs = result["probs"]
    assert set(probs) == set(EMOTIONS), "probs 키가 4종 감정과 다릅니다"
    assert abs(sum(probs.values()) - 1.0) < 1e-6, "probs 합이 1이 아닙니다"
    return result


if __name__ == "__main__":
    print(f"모델 폴더: {get_model_dir()}")

    start = time.perf_counter()
    warm_up()
    print(f"미리 불러오기: {(time.perf_counter() - start):.1f}초")

    for i, text in enumerate(["오늘 좀 지쳤어", "그냥 그래 ㅋㅋ", "커피 마시면서 쉬니까 편하다"], start=1):
        start = time.perf_counter()
        result = analyze_text(text, record_id=i)
        ms = (time.perf_counter() - start) * 1000
        print(json.dumps(result, ensure_ascii=False))
        print(f"  처리 시간: {ms:.0f}ms")

    # 빈 글은 거절되는지 확인
    try:
        analyze_text("   ")
    except ValueError as e:
        print(f"[빈 글 거절 확인] {e}")
