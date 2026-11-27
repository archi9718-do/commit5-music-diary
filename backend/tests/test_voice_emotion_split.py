"""학습/검증/평가 나누기 시험: 화자(나이+성별 묶음)와 문장이 세트 사이에 겹치지 않아야 합니다."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.split import split_rows

LABELS = ["좋음", "무난함", "가라앉음", "예민함"]


def fake_rows(groups, per_group, repeat_text_every=None):
    sizes = per_group if isinstance(per_group, list) else [per_group] * groups
    rows, i = [], 0
    for g, size in enumerate(sizes):
        for _ in range(size):
            text = f"문장{i % repeat_text_every}" if repeat_text_every else f"문장{i}"
            rows.append({"wav_path": f"{i}.wav", "text": text, "label": LABELS[i % 4], "group": f"{20 + g}|male"})
            i += 1
    return rows


def _by_split(out, key):
    return {s: {r[key] for r in out if r["split"] == s} for s in ("train", "val", "test")}


def test_groups_do_not_cross_splits():
    out, _ = split_rows(fake_rows(groups=36, per_group=20))
    by = _by_split(out, "group")
    assert all(by.values())
    assert not (by["train"] & by["val"]) and not (by["train"] & by["test"]) and not (by["val"] & by["test"])


def test_sentences_do_not_leak():
    out, _ = split_rows(fake_rows(groups=36, per_group=20, repeat_text_every=600))  # 120개 문장이 두 번씩 나옴
    t = _by_split(out, "text")
    assert t["test"] and t["val"] and t["train"]
    assert not (t["test"] & (t["val"] | t["train"])) and not (t["val"] & t["train"])


def test_split_is_deterministic():
    assert split_rows(fake_rows(36, 20), seed=1)[0] == split_rows(fake_rows(36, 20), seed=1)[0]


def test_split_reports_ratios():
    _, ratios = split_rows(fake_rows(groups=3, per_group=[100, 5, 5]))  # 큰 묶음 하나
    assert set(ratios) == {"train", "val", "test"} and abs(sum(ratios.values()) - 1) < 1e-9


def test_split_ratios_near_target():
    _, ratios = split_rows(fake_rows(groups=36, per_group=20))
    assert abs(ratios["test"] - 0.15) < 0.05 and abs(ratios["val"] - 0.15) < 0.05
