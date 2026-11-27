# evaluate.py
# 같은 문장으로 글만 / 목소리만 / 합친 것을 비교하고, 서비스에 켤지 판정합니다.
# w는 검증 세트로만 고르고, 평가(test) 세트는 마지막에 한 번만 봅니다.
# 결과는 저장소 밖(RESULT_DIR)에 저장하고, 모델 폴더의 meta.json에 켜기 판정을 씁니다.
import json
import time
from pathlib import Path

import numpy as np
import torch
from ai.emotion.emotion_mapper import EMOTIONS, HIGH
from ai.emotion.evaluate_f1 import f1_report

from .fuse import fuse
from .train import MODEL_DIR, load_split_features, macro_f1, predict_head

RESULT_DIR = Path(r"C:\work\moodwave_data\results\voice_emotion")
SHORT_LEN = 10  # 10자 이하 = 짧은 말
W_GRID = [round(i / 10, 1) for i in range(11)]
MIN_GAIN = 0.01  # 전체 macro-F1이 1%p 이상 올라야 켬


def _fused_preds(text_results, voice_probs, w):
    return [fuse(t, v, w)["emotion"] for t, v in zip(text_results, voice_probs)]


def choose_w(text_results: list[dict], voice_probs: list[dict], golds: list[str]) -> float:
    """W_GRID 중 macro-F1이 가장 높은 w. 같으면 작은 w (목소리를 덜 쓰는 쪽)."""
    best_w, best = 0.0, -1.0
    for w in W_GRID:
        score = macro_f1(golds, _fused_preds(text_results, voice_probs, w))
        if score > best:
            best_w, best = w, score
    return best_w


def bootstrap_lower(golds, preds_a, preds_b, n: int = 1000, seed: int = 42) -> float:
    """녹음을 한 줄씩 n번 다시 뽑아 macro_f1(b) − macro_f1(a)의 2.5% 분위수.
    같은 문장을 여러 사람이 녹음한 줄끼리 닮아서 구간이 실제보다 좁게 나올 수 있습니다."""
    rng = np.random.default_rng(seed)
    g, a, b = np.array(golds), np.array(preds_a), np.array(preds_b)
    diffs = []
    for _ in range(n):
        idx = rng.integers(0, len(g), len(g))
        diffs.append(macro_f1(list(g[idx]), list(b[idx])) - macro_f1(list(g[idx]), list(a[idx])))
    return float(np.quantile(diffs, 0.025))


def decide_enable(w: float, full_gain: float, full_lower: float, short_gain: float) -> bool:
    """설계 6절 기준: w>0, 전체 +1%p 이상이고 부트스트랩 아래쪽 >0, 짧은 말이 나빠지지 않음."""
    return w > 0 and full_gain >= MIN_GAIN and full_lower > 0 and short_gain >= 0


def pick(d: dict, short: bool) -> list[int]:
    return [i for i, s in enumerate(d["short"]) if s == short]


def sub(xs: list, idx: list[int]) -> list:
    return [xs[i] for i in idx]


def _confidence_table(results, golds):
    high = [(r["emotion"] == g) for r, g in zip(results, golds) if r["probs"][r["emotion"]] >= HIGH]
    return {"high_ratio": round(len(high) / len(golds), 4),
            "high_accuracy": round(sum(high) / len(high), 4) if high else None}


def main() -> None:
    from ai.emotion.service import analyze_text, warm_up

    meta_train = json.loads((Path(MODEL_DIR) / "train.json").read_text(encoding="utf-8"))
    encoder = meta_train["encoder"]
    d = load_split_features(encoder)
    head = torch.nn.Linear(d["train"][0].shape[1], len(EMOTIONS))
    head.load_state_dict(torch.load(Path(MODEL_DIR) / "head.pt"))

    warm_up()
    sets = {}
    for s in ("val", "test"):
        X, _, rows = d[s]
        keep = [i for i, r in enumerate(rows) if r["text"].strip()]  # 빈 문장은 글 모델에 넣을 수 없음
        if len(keep) < len(rows):
            print(f"{s}: 빈 문장 {len(rows) - len(keep)}개 제외")
        voice = predict_head(head, X[keep])
        sets[s] = {
            "golds": [rows[i]["label"] for i in keep],
            "short": [len(rows[i]["text"].strip()) <= SHORT_LEN for i in keep],
            "text": [analyze_text(rows[i]["text"]) for i in keep],
            "voice": [dict(zip(EMOTIONS, map(float, p))) for p in voice],
        }
        print(f"{s}: {len(keep)}문장 글 확률 완료", flush=True)

    v = sets["val"]
    w = choose_w(v["text"], v["voice"], v["golds"])
    vs, vl = pick(v, True), pick(v, False)
    w_short = choose_w(sub(v["text"], vs), sub(v["voice"], vs), sub(v["golds"], vs))
    w_long = choose_w(sub(v["text"], vl), sub(v["voice"], vl), sub(v["golds"], vl))
    print(f"검증에서 고른 w={w}, w_short={w_short}, w_long={w_long}")

    t = sets["test"]
    preds = {
        "text": [r["emotion"] for r in t["text"]],
        "voice": [max(p, key=p.get) for p in t["voice"]],
        "fused_w": _fused_preds(t["text"], t["voice"], w),
        "fused_len": [fuse(r, p, w_short if s else w_long)["emotion"]
                      for r, p, s in zip(t["text"], t["voice"], t["short"])],
    }
    ts = pick(t, True)
    table = {name: {"all": f1_report(t["golds"], p), "short": f1_report(sub(t["golds"], ts), sub(p, ts))}
             for name, p in preds.items()}

    full_gain = table["fused_w"]["all"]["macro_f1"] - table["text"]["all"]["macro_f1"]
    short_gain = table["fused_w"]["short"]["macro_f1"] - table["text"]["short"]["macro_f1"]
    full_lower = bootstrap_lower(t["golds"], preds["text"], preds["fused_w"])
    enabled = decide_enable(w, full_gain, full_lower, short_gain)
    confidence = {"text": _confidence_table(t["text"], t["golds"]),
                  "fused_w": _confidence_table([fuse(r, p, w) for r, p in zip(t["text"], t["voice"])], t["golds"])}

    print(f"\n평가 세트 {len(t['golds'])}문장 (짧은 말 {len(ts)}) — 인코더 {encoder}")
    print(f"{'방법':<10} {'전체 F1':>8} {'전체 정확도':>10} {'짧은 F1':>8} {'짧은 정확도':>10}")
    for name, r in table.items():
        print(f"{name:<10} {r['all']['macro_f1']:>8.4f} {r['all']['accuracy']:>10.4f} "
              f"{r['short']['macro_f1']:>8.4f} {r['short']['accuracy']:>10.4f}")
    print(f"전체 향상 {full_gain:+.4f} (부트스트랩 95% 아래쪽 {full_lower:+.4f}), 짧은 말 향상 {short_gain:+.4f}")
    print(f"확신도 '높음' (글만 / 합침): {confidence['text']} / {confidence['fused_w']}")
    print(f"켜기 판정: {'켬' if enabled else '끔'}")

    metrics = {"table": table, "full_gain": round(full_gain, 4), "full_lower": round(full_lower, 4),
               "short_gain": round(short_gain, 4), "confidence": confidence,
               "n_test": len(t["golds"]), "n_test_short": len(ts), "val_macro_f1": meta_train["val_macro_f1"]}
    meta = {"encoder": encoder, "w": w, "w_short": w_short, "w_long": w_long, "enabled": enabled,
            "metrics": metrics, "classes": list(EMOTIONS)}
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULT_DIR / f"{time.strftime('%Y%m%d-%H%M')}.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(MODEL_DIR) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}, {Path(MODEL_DIR) / 'meta.json'}")


if __name__ == "__main__":
    main()
