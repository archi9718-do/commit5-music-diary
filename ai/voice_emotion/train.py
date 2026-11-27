# train.py
# 인코더 특징(768차원) 위에 선형 층 하나(768 → 4)만 학습합니다. 인코더는 건드리지 않습니다.
# 두 인코더를 같은 조건으로 학습해 검증 macro-F1이 높은 쪽을 저장합니다. 평가(test) 세트는 읽지 않습니다.
# 저장소 최상위에서 python -m ai.voice_emotion.train 으로 실행합니다.
import json

import numpy as np
import torch
from ai.emotion.emotion_mapper import EMOTIONS
from ai.emotion.evaluate_f1 import f1_report

from .features import ENCODERS, FEATURE_DIR
from .split import SPLIT_CSV

MODEL_DIR = r"C:\work\moodwave_data\models\voice-emotion"
PATIENCE = 10
MAX_EPOCHS = 300


def macro_f1(golds: list[str], preds: list[str]) -> float:
    return f1_report(golds, preds)["macro_f1"]


def predict_head(head: torch.nn.Linear, X) -> np.ndarray:
    """(N, 4) softmax 확률, 열 순서는 EMOTIONS."""
    with torch.no_grad():
        return torch.softmax(head(torch.as_tensor(np.asarray(X, np.float32))), dim=1).numpy()


def _val_f1(head, X_val, y_val) -> float:
    preds = predict_head(head, X_val).argmax(1)
    return macro_f1([EMOTIONS[i] for i in y_val], [EMOTIONS[i] for i in preds])


def train_head(X_train, y_train, X_val, y_val, seed: int = 42, smoothing: float = 0.0) -> torch.nn.Linear:
    """클래스 가중치 교차 엔트로피 + Adam. 검증 macro-F1이 PATIENCE 에폭 동안 안 오르면 멈춥니다.
    y_train이 (N, 4) 비율이면 평가자 분포 자체를 정답으로 학습합니다 (클래스 가중치는 1위 감정 기준)."""
    torch.manual_seed(seed)
    X = torch.as_tensor(np.asarray(X_train, np.float32))
    y = torch.as_tensor(np.asarray(y_train))
    y = y.float() if y.ndim == 2 else y.long()
    hard = y.argmax(1) if y.ndim == 2 else y
    counts = torch.bincount(hard, minlength=len(EMOTIONS)).clamp(min=1).float()
    loss_fn = torch.nn.CrossEntropyLoss(weight=len(y) / (len(EMOTIONS) * counts), label_smoothing=smoothing)

    head = torch.nn.Linear(X.shape[1], len(EMOTIONS))
    opt = torch.optim.Adam(head.parameters(), lr=1e-3)
    gen = torch.Generator().manual_seed(seed)
    best, best_state, stale = -1.0, None, 0
    for _ in range(MAX_EPOCHS):
        for idx in torch.randperm(len(y), generator=gen).split(64):
            opt.zero_grad()
            loss_fn(head(X[idx]), y[idx]).backward()
            opt.step()
        score = _val_f1(head, X_val, y_val)
        if score > best:
            best, best_state, stale = score, {k: v.clone() for k, v in head.state_dict().items()}, 0
        else:
            stale += 1
            if stale >= PATIENCE:
                break
    head.load_state_dict(best_state)
    return head


def load_split_features(encoder: str):
    """{"train"|"val"|"test": (X, y 번호, 줄 목록)}. 특징 파일과 나누기 표를 wav_path로 맞춥니다."""
    import csv

    data = np.load(FEATURE_DIR / f"{encoder}.npz")
    feats = dict(zip(data["wav_path"], data["X"]))
    with open(SPLIT_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [r["wav_path"] for r in rows if r["wav_path"] not in feats]
    if missing:
        raise RuntimeError(f"{encoder}: 특징이 없는 녹음 {len(missing)}개 (features를 먼저 끝까지 실행)")
    out = {}
    for s in ("train", "val", "test"):
        part = [r for r in rows if r["split"] == s]
        out[s] = (np.stack([feats[r["wav_path"]] for r in part]),
                  np.array([EMOTIONS.index(r["label"]) for r in part]), part)
    return out


def main() -> None:
    from pathlib import Path

    scores, heads = {}, {}
    for enc in ENCODERS:
        d = load_split_features(enc)
        heads[enc] = train_head(d["train"][0], d["train"][1], d["val"][0], d["val"][1])
        scores[enc] = _val_f1(heads[enc], d["val"][0], d["val"][1])
        print(f"{enc}: 검증 macro-F1 {scores[enc]:.4f}", flush=True)

    best = max(scores, key=scores.get)
    out = Path(MODEL_DIR)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(heads[best].state_dict(), out / "head.pt")
    (out / "train.json").write_text(json.dumps(
        {"encoder": best, "val_macro_f1": scores, "seed": 42}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"고른 인코더: {best} → {out}")


if __name__ == "__main__":
    main()
