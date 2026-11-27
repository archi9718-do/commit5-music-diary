"""글 감정 결과와 목소리 확률 합치기 시험. 결과 양식(4종, 합 1, 둘째 자리)이 그대로여야 합니다."""

import copy
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.fuse import EMOTIONS, fuse

TEXT = {"record_id": None, "text": "뭐야", "probs": {"좋음": 0.1, "무난함": 0.5, "가라앉음": 0.1, "예민함": 0.3},
        "emotion": "무난함", "confidence": "중간"}
ANGRY = {"좋음": 0.0, "무난함": 0.0, "가라앉음": 0.0, "예민함": 1.0}


def test_fuse_w0_keeps_text():
    assert fuse(TEXT, ANGRY, 0.0) == TEXT


def test_fuse_changes_emotion_and_confidence():
    out = fuse(TEXT, ANGRY, 0.6)
    assert out["emotion"] == "예민함" and out["probs"]["예민함"] == 0.72 and out["confidence"] == "높음"
    assert out["record_id"] is None and out["text"] == "뭐야"


def test_fuse_extremes():
    for w in (0.3, 1.0):
        out = fuse(TEXT, {"좋음": 1.0, "무난함": 0.0, "가라앉음": 0.0, "예민함": 0.0}, w)
        assert set(out["probs"]) == set(EMOTIONS) and round(sum(out["probs"].values()), 10) == 1.0
        assert all(v == round(v, 2) for v in out["probs"].values())
    assert fuse(TEXT, {"좋음": 1.0, "무난함": 0.0, "가라앉음": 0.0, "예민함": 0.0}, 1.0)["emotion"] == "좋음"


def test_fuse_does_not_change_input():
    before = copy.deepcopy(TEXT)
    fuse(TEXT, ANGRY, 0.5)
    assert TEXT == before
