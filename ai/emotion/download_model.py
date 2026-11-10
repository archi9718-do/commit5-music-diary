# download_model.py
# 허깅페이스에서 감정 모델을 내려받아 원드라이브 밖 폴더에 저장하고, 예시 문장으로 시험해 봅니다.
import os

# 내려받는 임시 저장소(캐시)도 원드라이브 밖으로 지정 (transformers를 부르기 전에 설정해야 함)
os.environ["HF_HOME"] = r"C:\work\moodwave_data\hf_cache"

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "hun3359/klue-bert-base-sentiment"                     # 허깅페이스 모델 이름
SAVE_DIR = r"C:\work\moodwave_data\models\klue-bert-base-sentiment"  # 모델을 보관할 폴더

# 1) 내려받기: 처음 실행할 때만 인터넷에서 받고, 이후에는 저장된 것을 씀
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)               # 문장을 숫자로 바꿔 주는 도구
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

# 2) 정해 둔 폴더에 그대로 저장 (나중에 인터넷 없이도 이 폴더에서 불러올 수 있음)
tokenizer.save_pretrained(SAVE_DIR)
model.save_pretrained(SAVE_DIR)
print(f"저장 완료: {SAVE_DIR}")

# 3) 감정 종류 확인: 이 모델이 고를 수 있는 감정 목록
labels = model.config.id2label
print(f"감정 종류 개수: {len(labels)}")
for i in range(len(labels)):
    print(i, labels[i])

# 4) 예시 문장으로 시험
device = "cuda" if torch.cuda.is_available() else "cpu"             # GPU가 있으면 GPU 사용
model.to(device).eval()                                             # eval(): 학습이 아닌 사용 모드

sentences = ["오늘 좀 지쳤어", "그냥 그래 ㅋㅋ", "친구랑 놀아서 너무 신났어", "내일 발표라 너무 걱정돼"]
for text in sentences:
    inputs = tokenizer(text, return_tensors="pt").to(device)
    with torch.no_grad():                                           # 사용만 하므로 학습 계산은 끔
        probs = torch.softmax(model(**inputs).logits, dim=-1)[0]    # 감정별 확률(합이 1)
    top = torch.topk(probs, 3)                                      # 확률이 높은 3개만 뽑기
    result = ", ".join(f"{labels[i.item()]} {p.item():.2f}" for p, i in zip(top.values, top.indices))
    print(f"[{text}] → {result}")