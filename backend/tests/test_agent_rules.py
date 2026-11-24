"""추천 이유 규칙(위험 표현·템플릿·검사기) 시험. LLM을 부르지 않습니다."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent.rules import GENERIC_TEMPLATE, check_reasons, is_risk, template_reasons

RISK_FIXTURE = Path(__file__).parent / "fixtures" / "risk_sentences.json"
GOOD = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]


def lines(*texts, orders=(1, 2, 3)):
    return [{"recommend_order": o, "text": t} for o, t in zip(orders, texts)]


def test_risk_sentences_match_fixture():
    for case in json.loads(RISK_FIXTURE.read_text(encoding="utf-8")):
        assert is_risk(case["text"]) is case["risk"], case["text"]


def test_empty_text_is_not_risk():
    assert is_risk(None) is False and is_risk("") is False and is_risk("   ") is False


@pytest.mark.parametrize(("emotion", "steps"), [
    ("좋음", ["비슷한 분위기 1", "비슷한 분위기 2", "비슷한 분위기 3"]),
    ("무난함", ["비슷한 분위기 1", "비슷한 분위기 2", "비슷한 분위기 3"]),
    ("가라앉음", ["맞추기", "조금 밝게", "더 밝게"]),
    ("예민함", ["맞추기", "에너지 낮추기", "차분하고 조금 밝게"]),
])
def test_templates_pass_checker(emotion, steps):
    texts = template_reasons(emotion, steps)
    assert len(texts) == 3
    reasons = [{"recommend_order": i, "text": t} for i, t in enumerate(texts, 1)]
    assert check_reasons(reasons, emotion, has_recent=False) == (texts, [])


def test_unknown_step_uses_generic_template():
    assert template_reasons("좋음", ["없는 단계"]) == [GENERIC_TEMPLATE]


def test_generic_template_passes_checker_for_every_emotion():
    for emotion in ("좋음", "무난함", "가라앉음", "예민함"):
        assert check_reasons(lines(GENERIC_TEMPLATE, GENERIC_TEMPLATE, GENERIC_TEMPLATE), emotion, False)[1] == []


def test_strips_outer_whitespace():
    texts, problems = check_reasons(lines(*[f"  {t}\n" for t in GOOD]), "가라앉음", False)
    assert problems == [] and texts == GOOD


@pytest.mark.parametrize(("reasons", "code"), [
    (lines(*GOOD, orders=(1, 1, 3)), "format"),
    (lines(*GOOD[:2]), "format"),
    (lines("너무 짧아요.", *GOOD[1:]), "format"),
    (lines("지금 마음처럼 낮고\n잔잔한 곡으로 시작해요.", *GOOD[1:]), "format"),
    (lines("밝기 0.45인 곡으로 조금 밝게 이어가요.", *GOOD[1:]), "format"),
    (lines("힘내라는 마음으로 밝은 곡을 골랐어요.", *GOOD[1:]), "forbidden:힘내"),
    (lines("신나는 리듬으로 기분을 바꿔 보아요.", *GOOD[1:]), "emotion:신나"),
    (lines("잔잔한 피아노 소리로 마음을 달래요.", *GOOD[1:]), "song:피아노"),
    (lines("요즘 무거웠던 마음을 천천히 풀어요.", *GOOD[1:]), "recent:요즘"),
])
def test_checker_rejects(reasons, code):
    texts, problems = check_reasons(reasons, "가라앉음", has_recent=False)
    assert texts == [] and code in problems


def test_recent_word_ok_when_history_exists():
    reasons = lines("요즘 무거웠던 마음을 천천히 풀어요.", *GOOD[1:])
    assert check_reasons(reasons, "가라앉음", has_recent=True)[1] == []


def test_non_dict_items_are_format_problem():
    assert check_reasons(["문장", None, 3], "가라앉음", False) == ([], ["format"])
