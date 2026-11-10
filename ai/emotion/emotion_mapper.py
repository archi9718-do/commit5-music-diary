# emotion_mapper.py
# 공개 감정 모델(60가지)의 결과를 MoodWave 4종 감정과 확신도로 바꿔, 건호와 약속한 양식으로 내보냅니다.
import json
import time

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = r"C:\work\moodwave_data\models\klue-bert-base-sentiment"  # 어제 저장한 모델 폴더

# 60가지 감정 번호 → 4종 묶음 (번호는 download_model.py 출력 기준)
GROUPS = {
    "좋음":   [50, 51, 52, 54, 55, 58, 59],
    "무난함": [53, 56, 57],
    "가라앉음": list(range(10, 20)) + [30, 32, 33, 35, 36, 38, 39, 43, 44, 45, 48],
    "예민함": list(range(0, 10)) + [20, 21, 22, 23, 26, 27, 28, 29, 31, 37, 47],
}
EXCLUDED = [24, 25, 34, 40, 41, 42, 46, 49]  # 당황·놀람처럼 애매해서 뺀 감정

# 확신도 기준값 (검증 후 조정 가능)
HIGH = 0.6
MID = 0.4

# 묶음표 점검: 0~59번이 빠짐없이, 한 번씩만 들어갔는지 확인
all_ids = sorted(sum(GROUPS.values(), []) + EXCLUDED)
assert all_ids == list(range(60)), "묶음표에 빠지거나 겹친 번호가 있습니다"

# 모델 불러오기 (인터넷 없이 저장된 폴더에서)
device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).to(device).eval()


def get_confidence(top_prob: float) -> str:
    """가장 높은 확률로 확신도 3단계를 정합니다."""
    if top_prob >= HIGH:
        return "높음"   # 한 마디로 확인
    if top_prob >= MID:
        return "중간"   # 2개 중 고르기
    return "낮음"       # 4개 버튼


def predict_emotion(text: str, record_id=None) -> dict:
    """문장 하나를 받아 건호와 약속한 결과 양식(dict)으로 돌려줍니다."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128).to(device)
    with torch.no_grad():
        probs60 = torch.softmax(model(**inputs).logits, dim=-1)[0].cpu()  # 60가지 감정 확률

    # 묶음마다 확률 더하기
    sums = {name: probs60[ids].sum().item() for name, ids in GROUPS.items()}
    total = sum(sums.values())  # 제외한 감정을 뺀 나머지 합

    if total < 1e-6:  # 거의 모든 확률이 제외 감정에 몰린 경우: 판단 보류
        probs4 = {name: 0.25 for name in GROUPS}
    else:
        probs4 = {name: v / total for name, v in sums.items()}  # 4종 합이 1이 되도록 나누기

    emotion = max(probs4, key=probs4.get)  # 확률이 가장 높은 감정
    return {
        "record_id": record_id,
        "text": text,
        "probs": {k: round(v, 2) for k, v in probs4.items()},
        "emotion": emotion,
        "confidence": get_confidence(probs4[emotion]),
    }


if __name__ == "__main__":
    predict_emotion("준비 운동")  # 첫 실행은 GPU 준비 때문에 느려서 한 번 미리 돌려 둠

    samples = [
        "오늘 좀 지쳤어",
        "그냥 그래 ㅋㅋ",
        "친구랑 놀아서 너무 신났어",
        "내일 발표라 너무 걱정돼",
        "아무도 내 마음을 몰라줘서 외로워",
        "커피 마시면서 쉬니까 편하다",
    ]
    for i, text in enumerate(samples, start=1):
        start = time.perf_counter()
        result = predict_emotion(text, record_id=i)
        ms = (time.perf_counter() - start) * 1000  # 처리 시간(밀리초)
        print(json.dumps(result, ensure_ascii=False))  # ensure_ascii=False: 한글이 깨지지 않게
        print(f"  처리 시간: {ms:.0f}ms")