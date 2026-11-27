"""부감정 기준값 실험의 채점 함수 시험. 진짜 AI Hub 데이터는 쓰지 않습니다."""

import sys
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.secondary_threshold import chance, human_seconds, score, secondary

PROBS = {"좋음": 0.1, "무난함": 0.2, "가라앉음": 0.6, "예민함": 0.1}
VOTES = Counter({"가라앉음": 3, "무난함": 2})


def test_secondary_needs_threshold():
    assert secondary(PROBS, 0.2) == "무난함"
    assert secondary(PROBS, 0.25) is None


def test_human_seconds_skip_majority_and_few_votes():
    assert human_seconds(VOTES, "가라앉음", 2) == {"무난함"}
    assert human_seconds(Counter({"가라앉음": 3, None: 2}), "가라앉음", 1) == set()  # 혐오·공포·놀람 표


def test_score_and_chance():
    results = [{"probs": PROBS, "emotion": "가라앉음"}, {"probs": {**PROBS, "무난함": 0.1, "좋음": 0.2}, "emotion": "가라앉음"}]
    r = score(results, [VOTES, VOTES], ["가라앉음", "가라앉음"], 0.2)
    assert r["보여준_비율"] == 1.0 and r["맞음_2표이상"] == 0.5 and r["사람2표_찾은_비율"] == 0.5
    assert chance(results, [VOTES, VOTES], ["가라앉음", "가라앉음"]) == round(1 / 3, 4)
