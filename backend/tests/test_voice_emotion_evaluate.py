"""목소리 감정 평가 시험: 가중치 고르기, 부트스트랩, 켜기 판정. 모델 없이 가짜 확률로 돌아갑니다."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.evaluate import W_GRID, bootstrap_lower, choose_w, decide_enable

EMO = ["좋음", "무난함", "가라앉음", "예민함"]
GOLDS = EMO * 5


def _probs(top, high, low):
    return {k: (high if k == top else low) for k in EMO}


def _text(top, high=0.7, low=0.1):
    return {"record_id": None, "text": "글", "probs": _probs(top, high, low), "emotion": top, "confidence": "높음"}


def _wrong(g):
    return EMO[(EMO.index(g) + 1) % 4]


def test_w_grid_is_tenths():
    assert W_GRID == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def test_choose_w_prefers_smaller_on_tie():
    text = [_text(g) for g in GOLDS]                       # 글이 이미 다 맞음
    voice = [_probs(_wrong(g), 0.4, 0.2) for g in GOLDS]   # 목소리는 약하게 틀림
    assert choose_w(text, voice, GOLDS) == 0.0


def test_choose_w_picks_voice_when_text_wrong():
    text = [_text(_wrong(g), 0.28, 0.24) for g in GOLDS]   # 글은 거의 평평하게 틀림
    voice = [_probs(g, 1.0, 0.0) for g in GOLDS]           # 목소리는 확실히 맞음
    assert choose_w(text, voice, GOLDS) > 0.0


def test_bootstrap_lower_positive_when_b_always_better():
    assert bootstrap_lower(GOLDS, [_wrong(g) for g in GOLDS], GOLDS, n=200) > 0


def test_bootstrap_lower_zero_when_same():
    assert bootstrap_lower(GOLDS, GOLDS, GOLDS, n=50) == 0


def test_decide_enable_rules():
    assert decide_enable(0.3, 0.012, 0.001, 0.0)
    assert not decide_enable(0.0, 0.05, 0.02, 0.01)   # w=0
    assert not decide_enable(0.3, 0.009, 0.001, 0.0)  # 1%p 미만
    assert not decide_enable(0.3, 0.02, -0.001, 0.0)  # 구간이 0을 포함
    assert not decide_enable(0.3, 0.02, 0.01, -0.01)  # 짧은 말이 나빠짐
