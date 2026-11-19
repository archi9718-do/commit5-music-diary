# prepare_finetune_data.py
# S5: KcELECTRA 4종 미세조정용 학습/검증/시험 CSV를 만듭니다.
#   - 감성 대화 말뭉치(학습+검증 합침): 첫 문장(HS01), 당황·놀람 제외, 사람 번호(profile-id) 단위로 나눔
#   - KOTE: 평가자 3명 이상이 "없음"만 고른 댓글 → 무난함 (감정 없는 문장 보충)
# 결과는 저장소 밖(C:\work\moodwave_data\processed\finetune_v1)에 저장합니다.
import argparse
import csv
import json
import os
import random
import re
from collections import Counter, defaultdict

if __package__:
    from .emotion_mapper import EMOTIONS
    from .evaluate_f1 import ecode_to_emotion
else:
    from emotion_mapper import EMOTIONS
    from evaluate_f1 import ecode_to_emotion

DATA = r"C:\work\moodwave_data"
SENTI_FILES = [
    DATA + r"\raw\감성대화\Training_221115_add\라벨링데이터"
    r"\감성대화말뭉치(최종데이터)_Training\감성대화말뭉치(최종데이터)_Training.json",
    DATA + r"\raw\감성대화\Validation_221115_add\라벨링데이터"
    r"\감성대화말뭉치(최종데이터)_Validation\감성대화말뭉치(최종데이터)_Validation.json",
]
KOTE_FILE = DATA + r"\raw\KOTE\raw.json"
SHORT_EVAL = DATA + r"\processed\short_eval_v1.csv"
DEFAULT_OUT = DATA + r"\processed\finetune_v1"
SPLITS = ("train", "val", "test")
RATIO = (0.8, 0.1, 0.1)
KOTE_MIN_RATERS = 3  # 5명 중 3명 이상이 "없음"만 골라야 무난함으로 씀


def norm(text: str) -> str:
    """중복 비교용: 앞뒤 공백 제거, 여러 칸 공백은 한 칸으로."""
    return re.sub(r"\s+", " ", text).strip()


def hangul_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum("가" <= c <= "힣" for c in chars) / max(len(chars), 1)


def load_senti() -> list[dict]:
    rows = []
    for path in SENTI_FILES:
        with open(path, encoding="utf-8-sig") as f:
            for item in json.load(f):
                label = ecode_to_emotion(item["profile"]["emotion"]["type"])
                text = norm(item["talk"]["content"].get("HS01", ""))
                if label and text:  # label None = 당황·놀람 등 제외 감정
                    rows.append({"text": text, "label": label, "source": "감성대화",
                                 "group_id": "p_" + item["talk"]["id"]["profile-id"]})
    return rows


def load_kote() -> list[dict]:
    with open(KOTE_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    rows = []
    for cid, v in raw.items():
        n_none = sum(labels == ["없음"] for labels in v["labels"].values())
        text = norm(v["text"])
        # 뉴스 제목·목록·의미 없는 글을 줄이려고 길이와 한글 비율로 거름
        if n_none >= KOTE_MIN_RATERS and 5 <= len(text) <= 100 and hangul_ratio(text) >= 0.5:
            rows.append({"text": text, "label": "무난함", "source": "KOTE", "group_id": "k_" + cid})
    return rows


def split_by_group(rows: list[dict], seed: int) -> dict[str, list[dict]]:
    """같은 group_id(사람·댓글)는 한 묶음에만 들어가게 나눕니다."""
    groups = sorted({r["group_id"] for r in rows})
    random.Random(seed).shuffle(groups)
    cut1, cut2 = int(len(groups) * RATIO[0]), int(len(groups) * (RATIO[0] + RATIO[1]))
    where = {g: ("train" if i < cut1 else "val" if i < cut2 else "test") for i, g in enumerate(groups)}
    out = {s: [] for s in SPLITS}
    for r in rows:
        out[where[r["group_id"]]].append(r)
    return out


def dedupe(splits: dict[str, list[dict]], banned: set[str]) -> Counter:
    """여러 묶음에 걸친 문장, 정답이 엇갈리는 문장, 짧은 구어체 평가 문장을 지웁니다."""
    seen_split, seen_label = defaultdict(set), defaultdict(set)
    for s, rows in splits.items():
        for r in rows:
            seen_split[r["text"]].add(s)
            seen_label[r["text"]].add(r["label"])
    dropped = Counter()
    for s in SPLITS:
        kept, used = [], set()
        for r in splits[s]:
            t = r["text"]
            why = ("짧은 구어체 평가와 같음" if t in banned else
                   "정답 엇갈림" if len(seen_label[t]) > 1 else
                   "여러 묶음에 걸침" if len(seen_split[t]) > 1 else
                   "같은 묶음 안 중복" if t in used else "")
            if why:
                dropped[why] += 1
            else:
                kept.append(r)
                used.add(t)
        splits[s] = kept
    return dropped


def counts_table(splits: dict[str, list[dict]]) -> str:
    lines = ["| 묶음 | " + " | ".join(EMOTIONS) + " | 합계 | 그중 KOTE |", "|---" * (len(EMOTIONS) + 3) + "|"]
    for s in SPLITS:
        c = Counter(r["label"] for r in splits[s])
        kote = sum(r["source"] == "KOTE" for r in splits[s])
        lines.append(f"| {s} | " + " | ".join(f"{c[e]:,}" for e in EMOTIONS) + f" | {len(splits[s]):,} | {kote:,} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="미세조정용 4종 감정 CSV 만들기")
    parser.add_argument("--out", default=DEFAULT_OUT, help="결과 폴더 (저장소 밖)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    senti, kote = load_senti(), load_kote()
    print(f"감성대화 {len(senti):,}문장, KOTE 감정 없음 {len(kote):,}문장")

    # 두 자료를 따로 나눈 뒤 합침 → 각 자료가 80/10/10으로 고르게 들어감
    splits = {s: [] for s in SPLITS}
    for rows in (senti, kote):
        for s, part in split_by_group(rows, args.seed).items():
            splits[s] += part

    with open(SHORT_EVAL, encoding="utf-8-sig", newline="") as f:
        banned = {norm(r["text"]) for r in csv.DictReader(f)}
    dropped = dedupe(splits, banned)

    # 사람이 두 묶음에 걸치지 않았는지 점검 (사람별 분할의 핵심)
    owners = defaultdict(set)
    for s in SPLITS:
        for r in splits[s]:
            owners[r["group_id"]].add(s)
    assert all(len(v) == 1 for v in owners.values()), "한 사람(댓글)이 여러 묶음에 들어갔습니다"

    os.makedirs(args.out, exist_ok=True)
    for s in SPLITS:
        random.Random(args.seed).shuffle(splits[s])
        with open(os.path.join(args.out, f"{s}.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["text", "label", "source", "group_id"])
            w.writeheader()
            w.writerows(splits[s])

    table = counts_table(splits)
    note = "\n".join(f"- {k}: {v:,}문장" for k, v in dropped.items()) or "- 없음"
    with open(os.path.join(args.out, "counts.md"), "w", encoding="utf-8") as f:
        f.write(f"# finetune_v1 감정별 개수 (seed {args.seed})\n\n{table}\n\n## 지운 문장\n{note}\n")
    print(table)
    print("지운 문장:", dict(dropped))
    print(f"결과 저장 위치: {args.out}")


if __name__ == "__main__":
    main()
