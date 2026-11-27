# secondary_threshold.py
# 부감정(합친 확률의 2위)을 보여줄 기준값을 고릅니다. 정답은 평가자 5명 중 2명 이상이 고른 다른 감정.
# 임곗값 채점에는 검증 세트를 사용합니다. 결과는 저장소 밖 RESULT_PATH.
# 저장소 최상위에서 python -m ai.voice_emotion.secondary_threshold 로 실행합니다.
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from ai.emotion.emotion_mapper import EMOTIONS

from .compare_soft import load_votes
from .data import LABEL_MAP, RAW_DIR, VOTE_COLUMNS
from .fuse import fuse
from .train import MODEL_DIR, load_split_features, predict_head, train_head

THRESHOLDS = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
RESULT_PATH = Path(r"C:\work\moodwave_data\results\secondary_threshold.json")


def secondary(probs: dict[str, float], primary: str, threshold: float) -> str | None:
    """모델의 1위를 제외한 감정 중 확률이 기준값 이상인 가장 높은 감정."""
    second = max((label for label in probs if label != primary), key=probs.__getitem__)
    return second if probs[second] >= threshold else None


def human_seconds(counts: Counter, top: str, min_votes: int) -> set[str]:
    """다수결 감정 말고, min_votes표 이상 받은 4종 감정. 4종 밖 감정 표(None)는 셈하지 않음."""
    return {e for e, n in counts.items() if e and e != top and n >= min_votes}


def score(results: list[dict], votes: list[Counter], golds: list[str], threshold: float) -> dict:
    shown = []
    for result, vote, gold in zip(results, votes, golds, strict=True):
        primary = result["emotion"]
        second = secondary(result["probs"], primary, threshold)
        if second is not None:
            shown.append((second, primary, vote, gold))

    human_second_count = sum(bool(human_seconds(v, g, 2)) for v, g in zip(votes, golds))
    hit2 = sum(second in human_seconds(v, g, 2) for second, _, v, g in shown)
    hit1 = sum(second in human_seconds(v, g, 1) for second, _, v, g in shown)
    # 같은 녹음에서 모델의 1위를 뺀 감정 중 하나를 균등하게 고릅니다.
    random_hits = sum(len(human_seconds(v, g, 2) - {primary}) for _, primary, v, g in shown)
    shown_count = len(shown)
    return {
        "threshold": threshold,
        "보여준_비율": round(shown_count / len(results), 4),
        "맞음_2표이상": round(hit2 / shown_count, 4) if shown_count else None,
        "맞음_1표이상": round(hit1 / shown_count, 4) if shown_count else None,
        "무작위_기준": round(random_hits / ((len(EMOTIONS) - 1) * shown_count), 4) if shown_count else None,
        "사람2표_찾은_비율": round(hit2 / human_second_count, 4) if human_second_count else None,
    }


def main() -> None:
    import argparse

    from ai.emotion.service import analyze_text, warm_up

    parser = argparse.ArgumentParser(description="부감정 기준값 고르기 (검증 세트)")
    parser.add_argument("--soft", action="store_true", help="저장된 head.pt 대신 평가자 분포로 새로 학습한 head (저장 안 함)")
    args = parser.parse_args()

    meta = json.loads((Path(MODEL_DIR) / "meta.json").read_text(encoding="utf-8"))
    d = load_split_features(meta["encoder"])
    if args.soft:
        soft_votes = load_votes()
        soft = np.array([soft_votes[Path(r["wav_path"]).stem][0] for r in d["train"][2]], np.float32)
        head = train_head(d["train"][0], soft, d["val"][0], d["val"][1])
    else:
        head = torch.nn.Linear(d["train"][0].shape[1], len(EMOTIONS))
        head.load_state_dict(torch.load(Path(MODEL_DIR) / "head.pt"))

    with open(RAW_DIR / "5차년도_2차.csv", encoding="cp949", newline="") as f:
        all_votes = {r["wav_id"]: Counter(LABEL_MAP.get(r[c].strip().lower()) for c in VOTE_COLUMNS)
                     for r in csv.DictReader(f)}

    X, _, rows = d["val"]
    keep = [i for i, r in enumerate(rows) if r["text"].strip()]  # evaluate.py와 같게 빈 문장 제외
    voice = [dict(zip(EMOTIONS, map(float, p))) for p in predict_head(head, X[keep])]
    warm_up()
    text = [analyze_text(rows[i]["text"]) for i in keep]
    sources = {
        "목소리만": [{"probs": p, "emotion": max(p, key=p.get)} for p in voice],
        "합침": [fuse(t, p, meta["w"]) for t, p in zip(text, voice)],
    }
    votes = [all_votes[Path(rows[i]["wav_path"]).stem] for i in keep]
    golds = [rows[i]["label"] for i in keep]

    has2 = np.mean([bool(human_seconds(v, g, 2)) for v, g in zip(votes, golds)])
    print(f"검증 {len(golds)}문장, head={'분포' if args.soft else '다수결'}, w={meta['w']}, "
          f"사람이 2표 이상 준 다른 4종 감정이 있는 비율 {has2:.1%}")
    out = {"n_val": len(golds), "head": "분포" if args.soft else "다수결", "w": meta["w"], "사람2표_비율": float(has2)}
    for name, results in sources.items():
        out[name] = {"table": [score(results, votes, golds, t) for t in THRESHOLDS]}
        print(f"[{name}] 임곗값별 표시 비율과 일치율")
        for r in out[name]["table"]:
            print(" ", r)
    path = RESULT_PATH.with_stem(RESULT_PATH.stem + ("_soft" if args.soft else ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
