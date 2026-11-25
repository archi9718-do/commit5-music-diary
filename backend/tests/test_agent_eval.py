"""평가 스크립트의 경우 만들기·요약 시험 (API를 부르지 않음)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent.eval import build_cases, summarize


def test_build_cases_covers_emotions_and_histories():
    cases = build_cases()
    assert len(cases) == 12
    assert {c["facts"]["today"]["confirmed_emotion"] for c in cases} == {"좋음", "무난함", "가라앉음", "예민함"}
    assert {len(c["facts"]["recent_moods"]) for c in cases} == {0, 3}
    assert all(len(c["facts"]["songs"]) == 3 for c in cases)
    sad = next(c for c in cases if c["facts"]["today"]["confirmed_emotion"] == "가라앉음")
    assert [s["step"] for s in sad["facts"]["songs"]] == ["맞추기", "조금 밝게", "더 밝게"]


def test_summarize_counts_format_and_problems():
    rows = [
        {"stop": "ok", "problems": [], "tool_calls": ["get_today", "get_songs"], "usage": {"input_tokens": 1000, "output_tokens": 100}},
        {"stop": "checker", "problems": ["format", "song:피아노"], "tool_calls": ["get_songs"], "usage": {"input_tokens": 1000, "output_tokens": 100}},
        {"stop": "checker", "problems": ["emotion:신나"], "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}},
        {"stop": "error:ConnectionError", "problems": [], "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}},
    ]
    s = summarize(rows)
    assert s["runs"] == 4
    assert s["format_rate"] == 0.5  # 전체 실행 중 답을 받았고 형식 문제가 없는 비율 (오류·시간 초과는 실패로 셈)
    assert s["pass_rate"] == 0.25
    assert s["problem_counts"] == {"format": 1, "song:피아노": 1, "emotion:신나": 1}
    assert s["stop_counts"] == {"ok": 1, "checker": 2, "error:ConnectionError": 1}
    assert s["avg_tool_calls"] == 0.75
    assert abs(s["cost_usd"] - (2000 * 4 + 200 * 20) / 1_000_000) < 1e-9


def test_summarize_reports_time_and_over_deadline_rate():
    base = {"stop": "ok", "problems": [], "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}}
    rows = [{**base, "seconds": s} for s in (3.0, 5.0, 12.0, 4.0)]
    s = summarize(rows)
    assert s["median_seconds"] == 4.5 and s["max_seconds"] == 12.0
    assert s["over_deadline_rate"] == 0.25  # 서버 경로 10초 상한을 넘으면 화면엔 템플릿이 나감


def test_recheck_counts_direction_errors_and_human_labels(tmp_path):
    import csv

    from ai.agent.eval import recheck

    path = tmp_path / "old.csv"
    header = ["case", "run", "stop", "problems", "tool_calls", "seconds", "text1", "text2", "text3", "hallucination"]
    ok = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]
    wrong = [ok[0], "에너지를 낮춰 더 차분하게 이어가요.", ok[2]]  # 가라앉음 TARGETS 에너지는 0.30→0.32로 오름
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerow(["가라앉음-none", 1, "ok", "", "", 5.0, *ok, "0"])
        writer.writerow(["가라앉음-none", 2, "ok", "", "", 5.0, *wrong, "1"])
        writer.writerow(["가라앉음-none", 3, "ok", "", "", 5.0, *ok, ""])
        writer.writerow(["가라앉음-none", 4, "error:ConnectionError", "", "", 1.0, "", "", "", ""])
    result = recheck(path)
    assert result == {"checked": 3, "direction_errors": 1, "human_labeled": 2, "human_errors": 1}


def test_build_cases_can_use_real_recommended_songs():
    from ai.agent.eval import build_cases

    fixture = REPO_ROOT / "backend" / "tests" / "fixtures" / "sample_song_scores.csv"
    cases = build_cases(score_csv=fixture)
    good = next(c for c in cases if c["name"] == "좋음-none")["facts"]["songs"]
    # 실제 추천은 목표 좌표에서 벗어남: 좋음 1·2번 곡은 deam_8(0.81, 0.69) → deam_9(0.78, 0.72)
    assert [s["song_id"] for s in good] == ["deam_8", "deam_9", "deam_10"]
    assert (good[0]["brightness"], good[1]["brightness"]) == (0.81, 0.78)
    assert len(cases) == 12
