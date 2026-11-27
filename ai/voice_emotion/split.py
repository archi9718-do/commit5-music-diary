# split.py
# 학습/검증/평가 나누기. 화자 번호가 없으므로 나이+성별 묶음 단위로 나눕니다
# (한 화자의 나이·성별은 바뀌지 않으므로 같은 화자가 두 세트에 들어가지 않음).
# 같은 문장이 여러 번 녹음되어 있어, 평가 문장은 학습·검증에서, 검증 문장은 학습에서 뺍니다.
import csv
import random
from collections import Counter
from pathlib import Path

if __package__:
    from .data import RAW_DIR, load_rows
else:
    from data import RAW_DIR, load_rows

FEATURE_DIR = Path(r"C:\work\moodwave_data\features")
SPLIT_CSV = FEATURE_DIR / "split_set2.csv"
SPLITS = ("train", "val", "test")


def split_rows(rows: list[dict], seed: int = 42, ratios=(0.70, 0.15, 0.15)) -> tuple[list[dict], dict]:
    """각 줄에 "split"을 붙인 목록과 실제 비율을 돌려줍니다."""
    sizes = Counter(r["group"] for r in rows)
    groups = sorted(sizes)
    random.Random(seed).shuffle(groups)

    # 평가 → 검증 순서로 목표 줄 수에 닿을 때까지 묶음을 채우고, 나머지는 학습
    targets = {"test": ratios[2] * len(rows), "val": ratios[1] * len(rows)}
    assign, filled, order = {}, Counter(), ["test", "val"]
    for g in groups:
        while order and filled[order[0]] >= targets[order[0]]:
            order.pop(0)
        split = order[0] if order else "train"
        assign[g] = split
        filled[split] += sizes[g]

    out = [{**r, "split": assign[r["group"]]} for r in rows]
    test_text = {r["text"] for r in out if r["split"] == "test"}
    out = [r for r in out if r["split"] == "test" or r["text"] not in test_text]
    val_text = {r["text"] for r in out if r["split"] == "val"}
    out = [r for r in out if r["split"] != "train" or r["text"] not in val_text]

    counts = Counter(r["split"] for r in out)
    return out, {s: counts[s] / len(out) if out else 0.0 for s in SPLITS}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="5차 2차 세트를 학습/검증/평가로 나눠 CSV로 저장")
    # 51: seed 0~199 중 세 비율이 목표 ±5%p 안이고 검증·평가에 4종이 모두 있는 것 가운데 목표에 가장 가까움 (11/26)
    parser.add_argument("--seed", type=int, default=51)
    args = parser.parse_args()

    rows = load_rows(RAW_DIR / "5차년도_2차.csv", RAW_DIR / "5차년도_2차")
    out, ratios = split_rows(rows, seed=args.seed)
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SPLIT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["wav_path", "text", "label", "group", "split"])
        w.writeheader()
        w.writerows(out)

    print(f"seed {args.seed}: 다수결 4종 {len(rows)}줄 → 문장 제외 후 {len(out)}줄 → {SPLIT_CSV}")
    for s in SPLITS:
        part = [r for r in out if r["split"] == s]
        print(f"  {s}: {len(part)}줄 ({ratios[s]:.1%}), 묶음 {len({r['group'] for r in part})}개,",
              dict(Counter(r["label"] for r in part)))


if __name__ == "__main__":
    main()
