# evaluate_f1.py
# 감성 대화 말뭉치 검증 자료로 글 감정 모델의 4종 F1을 잽니다.
# 서버와 똑같은 predict_emotion()을 불러서, 서버가 실제로 내는 결과 그대로 채점합니다.
# 결과 파일은 저장소 밖(C:\work\moodwave_data\results)에 저장합니다.
import argparse
import csv
import json
import os
import time
from collections import Counter

if __package__:
    # python -m ai.emotion.evaluate_f1 로 실행할 때
    from .emotion_mapper import (
        EMOTIONS,
        GROUPS,
        HIGH,
        MID,
        get_model_dir,
        predict_emotion,
    )
else:
    # python ai/emotion/evaluate_f1.py 로 실행할 때
    from emotion_mapper import (
        EMOTIONS,
        GROUPS,
        HIGH,
        MID,
        get_model_dir,
        predict_emotion,
    )

DEFAULT_DATA = (
    r"C:\work\moodwave_data\raw\감성대화\Validation_221115_add\라벨링데이터"
    r"\감성대화말뭉치(최종데이터)_Validation\감성대화말뭉치(최종데이터)_Validation.json"
)
DEFAULT_OUT = r"C:\work\moodwave_data\results\f1_public_model"
CONFIDENCES = ("높음", "중간", "낮음")

# 모델 번호(0~59) → 4종 이름. E코드 − 10 = 모델 번호 (11/11 확인)
ID_TO_EMOTION = {i: name for name, ids in GROUPS.items() for i in ids}


def ecode_to_emotion(ecode: str):
    """E코드(예: E31)를 4종 감정으로 바꿉니다. 제외 감정이면 None."""
    model_id = int(ecode[1:]) - 10
    return ID_TO_EMOTION.get(model_id)


def load_csv_samples(path: str):
    """직접 만든 평가 CSV(text, gold, level 열)를 읽습니다. level은 쉬움/어려움 표시(없어도 됨)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = list(csv.DictReader(f))

    samples = []
    for i, row in enumerate(reader, start=1):
        text, gold = row["text"].strip(), row["gold"].strip()
        if gold not in EMOTIONS:  # 정답 이름 오타를 미리 잡음
            raise ValueError(f"{i}번째 줄 정답 '{gold}'이 4종 감정 이름이 아닙니다.")
        samples.append({
            "talk_id": f"short_{i:03d}",
            "profile_id": "",
            "text": text,
            "gold": gold,
            "ecode": "",
            "level": row.get("level", "").strip(),
        })
    return samples, len(reader), 0


def load_samples(path: str, field: str):
    """검증 JSON에서 (대화 번호, 사람 번호, 문장, 정답 감정, E코드)를 꺼냅니다."""
    if path.lower().endswith(".csv"):  # 직접 만든 짧은 구어체 평가 문장
        return load_csv_samples(path)
    with open(path, encoding="utf-8-sig") as f:  # utf-8-sig: 파일 앞 BOM 표시가 있어도 읽힘
        data = json.load(f)

    samples, excluded = [], 0
    for item in data:
        ecode = item["profile"]["emotion"]["type"]
        gold = ecode_to_emotion(ecode)
        if gold is None:  # 당황·놀람 같은 제외 감정은 채점에서 뺌
            excluded += 1
            continue
        text = item["talk"]["content"].get(field, "").strip()
        if not text:
            continue
        samples.append({
            "talk_id": item["talk"]["id"]["talk-id"],
            "profile_id": item["talk"]["id"]["profile-id"],
            "text": text,
            "gold": gold,
            "ecode": ecode,
        })
    return samples, len(data), excluded


def f1_report(golds, preds):
    """감정별 정밀도·재현율·F1과 매크로 F1, 가중 F1, 정확도를 계산합니다."""
    per_class = {}
    support = Counter(golds)
    for emo in EMOTIONS:
        tp = sum(1 for g, p in zip(golds, preds) if g == emo and p == emo)  # 맞게 고른 수
        pred_n = sum(1 for p in preds if p == emo)                         # 모델이 이 감정이라고 한 수
        gold_n = support[emo]                                              # 실제 이 감정인 수
        precision = tp / pred_n if pred_n else 0.0  # 이 감정이라고 했을 때 맞은 비율
        recall = tp / gold_n if gold_n else 0.0     # 실제 이 감정 중에 찾아낸 비율
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[emo] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": gold_n,
        }

    total = len(golds)
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(EMOTIONS)            # 감정 4개를 똑같이 평균
    weighted_f1 = sum(v["f1"] * v["support"] for v in per_class.values()) / total  # 문장 수만큼 가중 평균
    accuracy = sum(1 for g, p in zip(golds, preds) if g == p) / total
    return {
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "accuracy": round(accuracy, 4),
        "per_class": per_class,
    }


def confusion_matrix(golds, preds):
    """헷갈림 표: 행은 정답, 열은 모델 예측."""
    table = {g: {p: 0 for p in EMOTIONS} for g in EMOTIONS}
    for g, p in zip(golds, preds):
        table[g][p] += 1
    return table


def confidence_report(rows):
    """확신도별 개수와 정답률, "틀렸는데 높음" 비율을 계산합니다."""
    total = len(rows)
    report = {}
    for conf in CONFIDENCES:
        part = [r for r in rows if r["confidence"] == conf]
        correct = sum(1 for r in part if r["correct"])
        report[conf] = {
            "count": len(part),
            "share": round(len(part) / total, 4),                          # 전체 중 이 확신도 비율
            "accuracy": round(correct / len(part), 4) if part else None,   # 이 확신도일 때 정답률
        }

    wrong_high = sum(1 for r in rows if r["confidence"] == "높음" and not r["correct"])
    high_n = report["높음"]["count"]
    wrong_n = sum(1 for r in rows if not r["correct"])
    report["틀렸는데_높음"] = {
        "count": wrong_high,
        "of_all": round(wrong_high / total, 4),                         # 전체 문장 중
        "of_high": round(wrong_high / high_n, 4) if high_n else None,   # "높음" 판정 중 (버튼 1개만 보여 줬는데 틀린 비율)
        "of_wrong": round(wrong_high / wrong_n, 4) if wrong_n else None,  # 틀린 문장 중
    }
    return report


def threshold_sweep(rows):
    """"높음" 기준값을 바꿔 보면 어떻게 되는지 미리 계산합니다 (확신도 기준 조정용)."""
    sweep = []
    for th in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9):
        part = [r for r in rows if r["top_prob"] >= th]
        acc = sum(1 for r in part if r["correct"]) / len(part) if part else None
        sweep.append({
            "high_threshold": th,
            "high_share": round(len(part) / len(rows), 4),       # "높음"이 되는 문장 비율
            "high_accuracy": round(acc, 4) if acc is not None else None,  # 그때의 정답률
        })
    return sweep


def save_csv(path, rows, fields):
    # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않음
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="감성 대화 검증 자료로 4종 감정 F1 측정")
    parser.add_argument("--data", default=DEFAULT_DATA, help="검증 JSON 또는 평가 CSV 파일 위치")
    parser.add_argument("--out", default=DEFAULT_OUT, help="결과를 저장할 폴더 (저장소 밖)")
    parser.add_argument("--field", default="HS01", help="채점할 문장 칸 (기본: 사람문장1)")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 몇 문장만 시험 (0이면 전부)")
    args = parser.parse_args()

    samples, n_all, n_excluded = load_samples(args.data, args.field)
    if args.limit:
        samples = samples[: args.limit]
    print(f"전체 대화 {n_all}개, 제외 감정 {n_excluded}개 → 채점 {len(samples)}문장")
    print(f"정답 분포: {dict(Counter(s['gold'] for s in samples))}")
    print(f"모델 폴더: {get_model_dir()}")

    predict_emotion("준비 운동")  # 첫 예측만 느려서 미리 한 번 돌림

    rows = []
    start = time.perf_counter()
    for i, s in enumerate(samples, start=1):
        result = predict_emotion(s["text"])  # 서버와 같은 함수, 같은 결과 양식
        pred = result["emotion"]
        rows.append({
            **s,
            "pred": pred,
            "confidence": result["confidence"],
            "top_prob": result["probs"][pred],  # 반올림 후 값 (화면에 보이는 숫자)
            "correct": pred == s["gold"],
            **{f"p_{emo}": result["probs"][emo] for emo in EMOTIONS},
        })
        if i % 1000 == 0:
            print(f"  {i}/{len(samples)} 문장 처리")
    elapsed = time.perf_counter() - start

    golds = [r["gold"] for r in rows]
    preds = [r["pred"] for r in rows]
    summary = {
        "model_dir": get_model_dir(),
        "data": args.data,
        "field": args.field,
        "n_samples": len(rows),
        "n_excluded": n_excluded,
        "thresholds": {"high": HIGH, "mid": MID},
        "seconds": round(elapsed, 1),
        "ms_per_sentence": round(elapsed * 1000 / len(rows), 2),
        **f1_report(golds, preds),
        "confusion_matrix(row=정답,col=예측)": confusion_matrix(golds, preds),
        "confidence": confidence_report(rows),
        "high_threshold_sweep": threshold_sweep(rows),
    }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    fields = ["talk_id", "profile_id", "ecode", "level", "gold", "pred", "confidence", "top_prob",
              "correct", *[f"p_{emo}" for emo in EMOTIONS], "text"]
    save_csv(os.path.join(args.out, "predictions.csv"), rows, fields)
    wrong = sorted((r for r in rows if not r["correct"]), key=lambda r: -r["top_prob"])  # 자신 있게 틀린 것부터
    save_csv(os.path.join(args.out, "wrong_samples.csv"), wrong, fields)

    # 화면에 핵심만 출력
    print(f"\n처리 시간: {elapsed:.1f}초 (문장당 {summary['ms_per_sentence']}ms)")
    print(f"매크로 F1: {summary['macro_f1']}  (목표 0.60)")
    print(f"가중 F1: {summary['weighted_f1']}  정확도: {summary['accuracy']}")
    for emo, v in summary["per_class"].items():
        print(f"  {emo}: F1 {v['f1']}  정밀도 {v['precision']}  재현율 {v['recall']}  ({v['support']}문장)")
    conf = summary["confidence"]
    for c in CONFIDENCES:
        print(f"  확신도 {c}: {conf[c]['count']}문장 ({conf[c]['share']:.0%}), 정답률 {conf[c]['accuracy']}")
    wh = conf["틀렸는데_높음"]
    levels = sorted({r.get("level", "") for r in rows} - {""})
    for lv in levels:  # CSV에 쉬움/어려움 표시가 있으면 따로 정답률 출력
        part = [r for r in rows if r.get("level") == lv]
        acc = sum(1 for r in part if r["correct"]) / len(part)
        print(f"  [{lv}] {len(part)}문장, 정답률 {acc:.2f}")
    of_high = f"{wh['of_high']:.1%}" if wh["of_high"] is not None else "없음"  # "높음"이 0개일 때 대비
    print(f"  틀렸는데 높음: {wh['count']}문장, 높음 중 {of_high}, 전체 중 {wh['of_all']:.1%}")
    print(f"\n결과 저장 위치: {args.out}")


if __name__ == "__main__":
    main()