# emotion_mapper.py
# 공개 감정 모델(60가지)의 결과를 MoodWave 4종 감정과 확신도로 바꿔, 건호와 약속한 양식으로 내보냅니다.
import json
import os
import time

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# 모델 폴더: 환경 변수 MOODWAVE_MODEL_DIR가 있으면 그 값을, 없으면 기본 폴더를 씁니다.
DEFAULT_MODEL_DIR = r"C:\work\moodwave_data\models\klue-bert-base-sentiment"

# 서버(schemas.py)와 같은 4종 감정 이름
EMOTIONS = ("좋음", "무난함", "가라앉음", "예민함")

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

# 결과 양식의 소수 자리 (건호와 약속한 둘째 자리 유지)
DIGITS = 2

# 묶음표 점검: 0~59번이 빠짐없이, 한 번씩만 들어갔는지 확인
all_ids = sorted(sum(GROUPS.values(), []) + EXCLUDED)
assert all_ids == list(range(60)), "묶음표에 빠지거나 겹친 번호가 있습니다"
assert set(GROUPS) == set(EMOTIONS), "묶음 이름이 서버 감정 이름과 다릅니다"

# 모델은 파일을 불러올 때가 아니라, 처음 필요할 때 한 번만 읽습니다.
_tokenizer = None
_model = None
_device = None


def get_model_dir() -> str:
    """모델 폴더 위치를 돌려줍니다. 환경 변수가 우선입니다."""
    return os.environ.get("MOODWAVE_MODEL_DIR", DEFAULT_MODEL_DIR)


def load_model():
    """모델을 한 번만 불러오고, 이미 불러왔으면 그대로 돌려줍니다."""
    global _tokenizer, _model, _device
    if _model is None:  # 아직 안 불러온 경우에만 읽기
        model_dir = get_model_dir()
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(
                f"감정 모델 폴더가 없습니다: {model_dir} "
                "(MOODWAVE_MODEL_DIR 환경 변수나 download_model.py 실행 여부를 확인하세요)"
            )
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _tokenizer = AutoTokenizer.from_pretrained(model_dir)
        _model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(_device).eval()
    return _tokenizer, _model, _device


def get_confidence(top_prob: float) -> str:
    """가장 높은 확률로 확신도 3단계를 정합니다."""
    if top_prob >= HIGH:
        return "높음"   # 한 마디로 확인
    if top_prob >= MID:
        return "중간"   # 2개 중 고르기
    return "낮음"       # 4개 버튼


def fix_probs_sum(probs: dict, top: str, digits: int = DIGITS) -> dict:
    """반올림한 뒤 남는 오차를 가장 높은 감정(top)에 더해, 4종 합을 정확히 1로 맞춥니다."""
    rounded = {k: round(float(probs[k]), digits) for k in EMOTIONS}
    gap = 1.0 - sum(rounded.values())                 # 반올림 때문에 생긴 1과의 차이
    rounded[top] = round(rounded[top] + gap, digits)  # 차이를 가장 큰 값에 몰기
    return rounded


def predict_emotion(text: str, record_id=None) -> dict:
    """문장 하나를 받아 건호와 약속한 결과 양식(dict)으로 돌려줍니다."""
    tokenizer, model, device = load_model()  # 처음 한 번만 실제로 읽고, 이후는 바로 돌려받음

    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128).to(device)
    with torch.no_grad():
        probs60 = torch.softmax(model(**inputs).logits, dim=-1)[0].cpu()  # 60가지 감정 확률

    # 묶음마다 확률 더하기
    sums = {name: probs60[ids].sum().item() for name, ids in GROUPS.items()}
    total = sum(sums.values())  # 제외한 감정을 뺀 나머지 합

    if total < 1e-6:  # 거의 모든 확률이 제외 감정에 몰린 경우: 판단 보류
        probs4 = {name: 0.25 for name in EMOTIONS}
    else:
        probs4 = {name: v / total for name, v in sums.items()}  # 4종 합이 1이 되도록 나누기

    emotion = max(probs4, key=probs4.get)        # 확률이 가장 높은 감정 (반올림 전 값 기준)
    probs_out = fix_probs_sum(probs4, emotion)   # 반올림 + 합 1로 보정

    return {
        "record_id": record_id,
        "text": text,
        "probs": probs_out,
        "emotion": emotion,
        "confidence": get_confidence(probs_out[emotion]),  # 화면에 보이는 숫자와 같은 값으로 판단
    }


if __name__ == "__main__":
    print(f"모델 폴더: {get_model_dir()}")
    predict_emotion("준비 운동")  # 첫 실행은 모델 읽기와 GPU 준비 때문에 느려서 한 번 미리 돌려 둠

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
        total = sum(result["probs"].values())
        print(json.dumps(result, ensure_ascii=False))  # ensure_ascii=False: 한글이 깨지지 않게
        print(f"  처리 시간: {ms:.0f}ms, 확률합: {total:.4f}")
