# eval.py
# 추천 이유 에이전트 지표 측정 (README 8절): 형식 준수율, 검사기 통과율, 문제 종류, 109 안내 일치율.
# 실제 Claude API를 부르므로 비용이 듭니다. 실행 전에 예상 비용을 보여 주고 확인을 받습니다.
#
# 실행 (저장소 최상위에서): backend\.venv\Scripts\python.exe -m ai.agent.eval --runs 10
# 결과 CSV는 저장소 밖(C:\work\moodwave_data\agent_eval\)에 남깁니다. hallucination 칸은 사람이 읽고 채웁니다.
import argparse
import csv
import json
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT, REPO_ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ai.agent.rules import is_risk
from ai.agent.service import DEADLINE_SECONDS, write_reasons

from app.recommender import TARGETS  # 추천과 같은 단계 이름·좌표를 씀

PRICE_PER_MTOK = {"input_tokens": 4.0, "output_tokens": 20.0}  # claude-opus-5-5, US$
ESTIMATE_PER_RUN_USD = 0.02  # 11/24 측정: 24회 $0.435 (1회 약 $0.018)
EMOTIONS = ("좋음", "무난함", "가라앉음", "예민함")
RISK_FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "risk_sentences.json"
OUT_DIR = Path(os.environ.get("MOODWAVE_AGENT_EVAL_DIR", r"C:\work\moodwave_data\agent_eval"))


def build_cases() -> list[dict]:
    """감정 4종 × 최근 7일 (없음 / 같은 감정 3일 / 감정 3종 섞임) = 12경우."""
    histories = {
        "none": lambda emotion: [],
        "same": lambda emotion: [{"date": f"2026-11-{d}", "emotion": emotion} for d in (20, 21, 22)],
        "mixed": lambda emotion: [{"date": f"2026-11-{d}", "emotion": e}
                                  for d, e in zip((20, 21, 22), [x for x in EMOTIONS if x != emotion])],
    }
    cases = []
    for emotion in EMOTIONS:
        songs = [{"recommend_order": i, "song_id": f"deam_eval{i}", "step": step, "brightness": v, "energy": a}
                 for i, (v, a, step) in enumerate(TARGETS[emotion], 1)]
        for name, history in histories.items():
            cases.append({"name": f"{emotion}-{name}", "facts": {
                "today": {"confirmed_emotion": emotion, "taste_side": None},
                "songs": songs,
                "recent_moods": history(emotion),
            }})
    return cases


def summarize(rows: list[dict]) -> dict:
    runs = len(rows)
    answered = [r for r in rows if r["stop"] in ("ok", "checker")]
    problems = Counter(p for r in rows for p in r["problems"])
    tokens = {k: sum(r["usage"][k] for r in rows) for k in PRICE_PER_MTOK}
    return {
        "runs": runs,
        # 전체 실행 중 답을 받았고 형식 문제가 없는 비율 (오류·시간 초과는 실패로 셈)
        "format_rate": sum("format" not in r["problems"] for r in answered) / runs if runs else 0.0,
        "pass_rate": sum(r["stop"] == "ok" for r in rows) / runs if runs else 0.0,
        "problem_counts": dict(problems),
        "stop_counts": dict(Counter(r["stop"] for r in rows)),
        "avg_tool_calls": sum(len(r["tool_calls"]) for r in rows) / runs if runs else 0.0,
        "cost_usd": sum(tokens[k] * PRICE_PER_MTOK[k] for k in tokens) / 1_000_000,
        **_timing([r["seconds"] for r in rows if "seconds" in r]),
    }


def _timing(seconds: list[float]) -> dict:
    if not seconds:
        return {}
    # 서버 경로(backend/app/reasons.py)도 같은 10초에서 끊으므로, 넘은 비율 = 시연 때 템플릿이 나갈 비율
    return {"median_seconds": statistics.median(seconds), "max_seconds": max(seconds),
            "over_deadline_rate": sum(s > DEADLINE_SECONDS for s in seconds) / len(seconds)}


def risk_agreement() -> float:
    cases = json.loads(RISK_FIXTURE.read_text(encoding="utf-8"))
    return sum(is_risk(c["text"]) is c["risk"] for c in cases) / len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description="추천 이유 에이전트 지표 측정 (실제 API 호출)")
    parser.add_argument("--runs", type=int, default=10, help="경우마다 반복 횟수 (기본 10 → 120회)")
    parser.add_argument("--yes", action="store_true", help="비용 확인 없이 바로 실행")
    args = parser.parse_args()

    cases = build_cases()
    total = len(cases) * args.runs
    print(f"{len(cases)}경우 × {args.runs}번 = {total}회 호출, 예상 약 ${total * ESTIMATE_PER_RUN_USD:.2f}")
    if not args.yes and input("진행할까요? (y/N) ").strip().lower() != "y":
        print("취소했습니다.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{datetime.now():%Y%m%d-%H%M}.csv"
    rows = []
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case", "run", "stop", "problems", "tool_calls", "seconds", "text1", "text2", "text3", "hallucination"])
        for case in cases:
            for run in range(1, args.runs + 1):
                started = time.perf_counter()
                result = write_reasons(case["facts"])
                result["seconds"] = round(time.perf_counter() - started, 2)
                rows.append(result)
                texts = result["texts"] or ["", "", ""]
                writer.writerow([case["name"], run, result["stop"], " ".join(result["problems"]),
                                 " ".join(result["tool_calls"]), result["seconds"], *texts, ""])
                handle.flush()
                print(f"{len(rows)}/{total} {case['name']} #{run}: {result['stop']} {result['seconds']}s")

    summary = summarize(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"109 안내: 위험 문장 판단 일치율 {risk_agreement():.0%} (화면 쪽은 frontend npm test가 확인)")
    print(f"CSV: {out_path}  → 검사기 통과(stop=ok) 줄의 hallucination 칸을 읽고 채우세요")


if __name__ == "__main__":
    main()
