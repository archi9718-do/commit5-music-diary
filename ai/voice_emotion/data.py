# data.py
# AI Hub "감정 분류를 위한 대화 음성" CSV를 읽어 5명 중 3명 이상이 고른 감정(다수결)만 남깁니다.
# 원본 데이터는 재배포 금지라 저장소 밖(RAW_DIR)에만 둡니다. torch를 쓰지 않습니다.
import csv
from collections import Counter
from pathlib import Path

RAW_DIR = Path(r"C:\work\moodwave_data\raw")

# AI Hub 라벨(소문자) → MoodWave 4종. 혐오·공포·놀람은 4종에 대응하지 않아 뺍니다.
LABEL_MAP = {"happiness": "좋음", "neutral": "무난함", "sadness": "가라앉음", "angry": "예민함"}

VOTE_COLUMNS = [f"{i}번 감정" for i in range(1, 6)]  # 세기 열(4번만 "4번감정세기")은 읽지 않음
MIN_VOTES = 3


def majority_label(votes: list[str]) -> str | None:
    """5명의 감정 표시 중 같은 값이 3개 이상이면 4종 이름으로, 아니면 None."""
    counts = Counter(v.strip().lower() for v in votes if v and v.strip())
    if not counts:
        return None
    label, n = counts.most_common(1)[0]
    return LABEL_MAP.get(label) if n >= MIN_VOTES else None


def soft_label(votes: list[str]) -> list[float] | None:
    """5명 표 중 4종 표만 세어 EMOTIONS 순서의 비율로. 4종 표가 없으면 None. 혐오·공포·놀람 표는 버립니다."""
    from ai.emotion.emotion_mapper import EMOTIONS

    counts = Counter(LABEL_MAP.get(v.strip().lower()) for v in votes if v and v.strip())
    total = sum(n for k, n in counts.items() if k)
    return [counts[e] / total for e in EMOTIONS] if total else None


def load_rows(csv_path: Path, wav_dir: Path) -> list[dict]:
    """다수결이 있고 wav 파일이 있는 줄만 {"wav_path","text","label","group"}으로 돌려줍니다."""
    wavs = {p.stem: p for p in Path(wav_dir).rglob("*.wav")}  # 5차는 하위 폴더에 있음
    rows = []
    with open(csv_path, encoding="cp949", newline="") as f:
        for r in csv.DictReader(f):
            label = majority_label([r[c] for c in VOTE_COLUMNS])
            wav = wavs.get(r["wav_id"])
            if label is None or wav is None:
                continue
            rows.append({"wav_path": str(wav), "text": r["발화문"], "label": label,
                         "group": f"{r['나이']}|{r['성별']}"})
    return rows
