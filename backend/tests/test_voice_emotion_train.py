"""목소리 감정 분류기(선형 층 1개) 학습 시험. 가짜 특징으로 돌아갑니다."""

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.train import EMOTIONS, macro_f1, predict_head, train_head


def separable_blobs(n, dim, classes, seed):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, classes, n)
    centers = rng.normal(0, 3, (classes, dim))
    return (centers[y] + rng.normal(0, 1, (n, dim))).astype(np.float32), y


def test_macro_f1_matches_simple_case():
    assert macro_f1(["좋음", "무난함", "가라앉음", "예민함"], ["좋음", "무난함", "가라앉음", "예민함"]) == 1.0
    assert macro_f1(["좋음", "좋음"], ["무난함", "무난함"]) == 0.0


def test_train_head_learns_separable_data():
    X, y = separable_blobs(n=400, dim=768, classes=4, seed=0)
    head = train_head(X[:300], y[:300], X[300:], y[300:])
    probs = predict_head(head, X[300:])
    assert probs.shape == (100, 4) and np.allclose(probs.sum(1), 1, atol=1e-5)
    assert macro_f1([EMOTIONS[i] for i in y[300:]], [EMOTIONS[i] for i in probs.argmax(1)]) > 0.9


def test_train_head_handles_imbalance():
    X, y = separable_blobs(n=600, dim=16, classes=4, seed=1)
    keep = (y != 3) | (np.arange(len(y)) % 10 == 0)  # 예민함을 1/10만 남김
    X, y = X[keep], y[keep]
    head = train_head(X[:-100], y[:-100], X[-100:], y[-100:])
    assert (predict_head(head, X[y == 3]).argmax(1) == 3).mean() > 0.5  # 적은 감정도 고를 수 있어야 함


def test_train_head_accepts_soft_targets():
    X, y = separable_blobs(n=400, dim=16, classes=4, seed=2)
    soft = np.full((len(y), 4), 0.1, np.float32)
    soft[np.arange(len(y)), y] = 0.7  # 1위 0.7, 나머지 0.1씩
    head = train_head(X[:300], soft[:300], X[300:], y[300:])
    assert macro_f1([EMOTIONS[i] for i in y[300:]], [EMOTIONS[i] for i in predict_head(head, X[300:]).argmax(1)]) > 0.9
