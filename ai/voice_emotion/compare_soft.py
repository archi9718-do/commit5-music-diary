# compare_soft.py
# 다수결(1위 감정 하나) 학습과 평가자 5명의 분포 학습을 같은 조건으로 비교합니다.
# 대조군: 다수결 + label smoothing 0.1 (분포 학습의 이득이 "정답을 덜 확신하게 만든 효과"뿐인지 가르기 위해).
# 검증 세트만 봅니다. 평가(test) 세트는 읽지 않습니다. 결과는 저장소 밖 RESULT_PATH.
# 저장소 최상위에서 python -m ai.voice_emotion.compare_soft 로 실행합니다.
import csv
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path

import numpy as np
from ai.emotion.emotion_mapper import EMOTIONS

from .data import RAW_DIR, VOTE_COLUMNS, soft_label
from .train import load_split_features, macro_f1, predict_head, train_head

ENCODER = "hubert"  # train.py가 검증 macro-F1로 고른 인코더 (train.json)
SEEDS = (0, 1, 2, 3, 4)
RESULT_PATH = Path(r"C:\work\moodwave_data\results\compare_soft.json")


def ece(probs: np.ndarray, y: np.ndarray, bins: int = 15) -> float:
    """기대 보정 오차: 1위 확률이 실제 정답률과 얼마나 어긋나는지 (0이 완벽)."""
    conf, pred = probs.max(1), probs.argmax(1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in pairwise(edges):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(total)


def load_votes() -> dict[str, tuple[list[float], int]]:
    """wav_id → (4종 분포, 1위 감정 득표수)."""
    out = {}
    with open(RAW_DIR / "5차년도_2차.csv", encoding="cp949", newline="") as f:
        for r in csv.DictReader(f):
            votes = [r[c] for c in VOTE_COLUMNS]
            soft = soft_label(votes)
            if soft:
                top = Counter(v.strip().lower() for v in votes if v and v.strip()).most_common(1)[0][1]
                out[r["wav_id"]] = (soft, top)
    return out


def score(probs, y, top_votes) -> dict:
    names = lambda idx: [EMOTIONS[i] for i in idx]
    pred = probs.argmax(1)
    split3 = top_votes == 3
    return {
        "macro_f1": macro_f1(names(y), names(pred)),
        "accuracy": float((pred == y).mean()),
        "ece": ece(probs, y),
        "macro_f1_3표": macro_f1(names(y[split3]), names(pred[split3])),
        "macro_f1_4~5표": macro_f1(names(y[~split3]), names(pred[~split3])),
    }


def main() -> None:
    d = load_split_features(ENCODER)
    votes = load_votes()
    soft, top = {}, {}
    for s in ("train", "val"):
        ids = [Path(r["wav_path"]).stem for r in d[s][2]]
        soft[s] = np.array([votes[i][0] for i in ids], np.float32)
        top[s] = np.array([votes[i][1] for i in ids])
        assert (soft[s].argmax(1) == d[s][1]).all(), "분포의 1위와 다수결 라벨이 다릅니다"
    (X_tr, y_tr, _), (X_val, y_val, _) = d["train"], d["val"]

    arms = {
        "다수결": lambda seed: train_head(X_tr, y_tr, X_val, y_val, seed=seed),
        "다수결+smoothing0.1": lambda seed: train_head(X_tr, y_tr, X_val, y_val, seed=seed, smoothing=0.1),
        "분포": lambda seed: train_head(X_tr, soft["train"], X_val, y_val, seed=seed),
    }
    results = {}
    for name, fit in arms.items():
        runs = [score(predict_head(fit(seed), X_val), y_val, top["val"]) for seed in SEEDS]
        results[name] = {k: {"mean": float(np.mean([r[k] for r in runs])), "std": float(np.std([r[k] for r in runs]))}
                         for k in runs[0]}
        print(name, {k: f"{v['mean']:.4f}±{v['std']:.4f}" for k, v in results[name].items()}, flush=True)

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(
        {"encoder": ENCODER, "seeds": SEEDS, "n_train": len(y_tr), "n_val": len(y_val),
         "val_3표_비율": float((top["val"] == 3).mean()), "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {RESULT_PATH}")


if __name__ == "__main__":
    main()
