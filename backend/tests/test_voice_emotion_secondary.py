"""부감정 기준값 실험의 채점 함수 시험. 진짜 AI Hub 데이터는 쓰지 않습니다."""

import sys
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.fuse import EMOTIONS, fuse
from ai.voice_emotion.secondary_threshold import human_seconds, score, secondary

PROBS = {"좋음": 0.1, "무난함": 0.2, "가라앉음": 0.6, "예민함": 0.1}
VOTES = Counter({"가라앉음": 3, "무난함": 2})


def test_secondary_needs_threshold():
    assert secondary(PROBS, "가라앉음", 0.2) == "무난함"
    assert secondary(PROBS, "가라앉음", 0.25) is None


def test_secondary_excludes_fused_primary_on_rounding_tie():
    text = {"probs": dict.fromkeys(EMOTIONS, 0.25)}
    voice = dict(zip(EMOTIONS, (0.467, 0.469, 0.035, 0.029), strict=True))
    result = fuse(text, voice, 0.7)

    assert result["probs"]["좋음"] == result["probs"]["무난함"] == 0.40
    assert result["emotion"] == "무난함"
    assert secondary(result["probs"], result["emotion"], 0.40) == "좋음"

    votes = Counter({"좋음": 3, "무난함": 2})
    row = score([result], [votes], ["좋음"], 0.40)
    assert row["맞음_2표이상"] == row["무작위_기준"] == 0.0


def test_human_seconds_skip_majority_and_few_votes():
    assert human_seconds(VOTES, "가라앉음", 2) == {"무난함"}
    assert human_seconds(Counter({"가라앉음": 3, None: 2}), "가라앉음", 1) == set()  # 혐오·공포·놀람 표


def test_score_and_chance():
    results = [
        {"probs": PROBS, "emotion": "가라앉음"},
        {"probs": {**PROBS, "무난함": 0.1, "좋음": 0.2}, "emotion": "가라앉음"},
    ]
    r = score(results, [VOTES, VOTES], ["가라앉음", "가라앉음"], 0.2)
    assert r["보여준_비율"] == 1.0
    assert r["맞음_2표이상"] == r["사람2표_찾은_비율"] == 0.5
    assert r["무작위_기준"] == round(1 / 3, 4)


def test_random_baseline_uses_rows_shown_at_each_threshold():
    results = [
        {"probs": {**PROBS, "무난함": 0.3, "가라앉음": 0.5}, "emotion": "가라앉음"},
        {"probs": PROBS, "emotion": "가라앉음"},
    ]
    votes = [VOTES, Counter({"가라앉음": 5})]
    golds = ["가라앉음", "가라앉음"]

    both = score(results, votes, golds, 0.2)
    assert both["보여준_비율"] == 1.0
    assert both["무작위_기준"] == round(1 / 6, 4)

    one = score(results, votes, golds, 0.3)
    assert one["보여준_비율"] == 0.5
    assert one["맞음_2표이상"] == 1.0
    assert one["무작위_기준"] == round(1 / 3, 4)

    none = score(results, votes, golds, 0.35)
    assert none["보여준_비율"] == 0.0
    assert none["맞음_2표이상"] is None
    assert none["무작위_기준"] is None
