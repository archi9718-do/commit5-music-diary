"""추천 이유 규칙(위험 표현·템플릿·검사기) 시험. LLM을 부르지 않습니다."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent.rules import (
    GENERIC_TEMPLATE,
    TEMPLATE_CLAIMS,
    TEMPLATES,
    check_reasons,
    is_risk,
    template_reasons,
)

from app.recommender import TARGETS

RISK_FIXTURE = Path(__file__).parent / "fixtures" / "risk_sentences.json"
GOOD = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]


def lines(*texts, orders=(1, 2, 3)):
    return [{"recommend_order": o, "text": t} for o, t in zip(orders, texts)]


def target_songs(emotion):
    return [{"recommend_order": i, "step": step, "brightness": b, "energy": e}
            for i, (b, e, step) in enumerate(TARGETS[emotion], 1)]


def test_risk_sentences_match_fixture():
    for case in json.loads(RISK_FIXTURE.read_text(encoding="utf-8")):
        assert is_risk(case["text"]) is case["risk"], case["text"]


def test_empty_text_is_not_risk():
    assert is_risk(None) is False and is_risk("") is False and is_risk("   ") is False


@pytest.mark.parametrize("emotion", TARGETS)
def test_templates_on_target_scores_pass_checker(emotion):
    songs = target_songs(emotion)
    texts = template_reasons(emotion, songs)
    assert texts == [TEMPLATES[emotion, song["step"]] for song in songs]
    assert check_reasons(lines(*texts), emotion, has_recent=False, songs=songs) == (texts, [])


def test_unknown_step_uses_generic_template():
    songs = [{**song, "step": "없는 단계"} for song in target_songs("좋음")]
    assert template_reasons("좋음", songs) == [GENERIC_TEMPLATE] * 3


# 건호 2차 리뷰(#27): 템플릿도 실제 점수와 안 맞으면 비교 없는 문장으로. index번째 곡만 바꿔 그 줄의 주장을 깸
@pytest.mark.parametrize(("emotion", "index", "scores"), [
    ("좋음", 1, {"brightness": 0.50}),  # "비슷한 밝기"인데 크게 어두움
    ("좋음", 2, {"energy": 0.20}),  # "같은 분위기"인데 에너지가 크게 다름
    ("무난함", 1, {"energy": 0.90}),
    ("가라앉음", 1, {"brightness": 0.20}),  # "밝기를 올려"인데 그대로
    ("가라앉음", 2, {"brightness": 0.30}),
    ("예민함", 1, {"energy": 0.90}),
    ("예민함", 2, {"energy": 0.60}),
    ("예민함", 2, {"brightness": 0.10}),
])
def test_template_against_actual_scores_becomes_generic(emotion, index, scores):
    songs = target_songs(emotion)
    songs[index].update(scores)
    texts = template_reasons(emotion, songs)
    assert texts[index] == GENERIC_TEMPLATE
    assert texts[0] == TEMPLATES[emotion, songs[0]["step"]]


def test_template_claim_covers_every_comparing_step():
    later = {(emotion, step) for emotion, stages in TARGETS.items() for _, _, step in stages[1:]}
    assert set(TEMPLATE_CLAIMS) == later


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


# 건호 리뷰(#27): 2번 곡이 1번보다 밝기·에너지가 낮은데 "더 밝고 힘찬"이 통과하던 문제
DOWN = [{"recommend_order": 1, "brightness": 0.60, "energy": 0.70},
        {"recommend_order": 2, "brightness": 0.50, "energy": 0.55},
        {"recommend_order": 3, "brightness": 0.45, "energy": 0.40}]
UP = [{"recommend_order": 1, "brightness": 0.20, "energy": 0.30},
      {"recommend_order": 2, "brightness": 0.45, "energy": 0.32},
      {"recommend_order": 3, "brightness": 0.70, "energy": 0.35}]
FIRST = "지금 마음처럼 잔잔한 곡으로 시작해요."


@pytest.mark.parametrize(("second", "code"), [
    ("앞 곡보다 더 밝고 힘찬 곡으로 이어가요.", "direction:밝기"),
    ("앞 곡보다 더 밝고 힘찬 곡으로 이어가요.", "direction:에너지"),
    ("밝기를 조금 올려 밝게 이어가요.", "direction:밝기"),
    ("에너지를 올려 더 활기차게 이어가요.", "direction:에너지"),
])
def test_direction_claim_against_lower_scores_is_rejected(second, code):
    texts, problems = check_reasons(lines(FIRST, second, GOOD[2].replace("밝은", "차분한")), "가라앉음", False, songs=DOWN)
    assert texts == [] and code in problems


def test_direction_claim_matching_scores_passes():
    reasons = lines(FIRST, "조금 더 밝게 천천히 이어가요.", "한층 더 밝은 곡으로 오늘을 마무리해요.")
    assert check_reasons(reasons, "가라앉음", False, songs=UP)[1] == []


def test_calmer_claim_needs_lower_energy():
    reasons = lines(FIRST, "에너지를 낮춰 더 차분하게 이어가요.", "한층 더 밝은 곡으로 오늘을 마무리해요.")
    assert "direction:에너지" in check_reasons(reasons, "가라앉음", False, songs=UP)[1]  # UP은 에너지 0.30→0.32
    assert "direction:에너지" not in check_reasons(reasons, "가라앉음", False, songs=DOWN)[1]


def test_first_line_and_unchanged_words_are_not_direction_claims():
    reasons = lines("지금처럼 밝고 힘찬 곡으로 시작해요.", "차분함은 그대로 두고 이어가요.", "잔잔한 흐름으로 오늘을 마무리해요.")
    assert check_reasons(reasons, "가라앉음", False, songs=DOWN)[1] == []


@pytest.mark.parametrize(("second", "code", "songs"), [
    ("앞 곡보다 살짝 덜 밝은 곡으로 이어가요.", "direction:밝기", UP),  # UP은 밝기가 오름
    ("앞 곡보다 한결 차분해진 곡으로 이어가요.", "direction:에너지", UP),  # UP은 에너지가 오름
    ("앞 곡보다 차분해지며 천천히 이어가요.", "direction:에너지", UP),
    ("앞 곡보다 덜 활기찬 곡으로 이어가요.", "direction:에너지", UP),
])
def test_softer_comparatives_are_checked(second, code, songs):
    reasons = lines(FIRST, second, "한층 더 밝은 곡으로 오늘을 마무리해요.")
    assert code in check_reasons(reasons, "가라앉음", False, songs=songs)[1]


def test_softer_comparatives_matching_scores_pass():
    reasons = lines(FIRST, "앞 곡보다 살짝 덜 밝고 한결 차분해진 곡이에요.", "잔잔한 흐름으로 오늘을 마무리해요.")
    assert check_reasons(reasons, "가라앉음", False, songs=DOWN)[1] == []


@pytest.mark.parametrize("second", [
    "앞 곡보다 살짝 덜 밝게 흐르는 곡이에요",  # "밝게"가 들어 있어도 어두워졌다는 말
    "앞 곡보다 덜 힘찬 흐름으로 이어지는 곡이에요",
    "앞 곡보다 덜 활기차게 이어지는 곡이에요",
])
def test_less_than_phrases_are_read_as_decrease(second):
    reasons = lines(FIRST, second, "잔잔한 흐름으로 오늘을 마무리해요.")
    assert check_reasons(reasons, "가라앉음", False, songs=DOWN)[1] == []
    assert any(p.startswith("direction:") for p in check_reasons(reasons, "가라앉음", False, songs=UP)[1])


# 11/25 판정에서 지어낸 말로 본 문장: 곡이 기분·몸을 바꿔 준다고 말함 (도구 결과에 없는 내용)
@pytest.mark.parametrize("text", [
    "가장 밝으면서도 조금 차분하게 좋은 기분을 감싸 줘요",
    "한층 더 밝은 쪽으로 마음을 이끌어요",
    "한층 더 밝은 쪽으로 데려가는 곡이에요",
    "앞 곡보다 조금 더 밝아져 마음을 살며시 들어 올려요",
    "앞 곡보다 조금 더 밝아져서 마음이 살며시 올라와요",
    "한층 더 밝아지고 조금 더 올라 기분을 띄워 줘요",
    "한층 더 밝아지고 조금 더 올라 기분을 끌어올려요",
    "한층 더 밝은 흐름으로 기분을 환하게 이어 가요",
    "한층 더 밝은 흐름으로 좋은 기분을 머금게 해요",
    "이어서 조금 밝은 곡으로 날카로움을 덜어 봐요",
    "이어서 조금 밝은 곡으로 날 선 기분을 덜어 봤어요",
    "조금 더 밝은 곡으로 날선 마음을 누그러뜨려요",
    "조금 더 밝은 곡으로 마음을 부드럽게 풀어 줘요",
    "앞 곡보다 한결 밝은 곡으로 숨을 고를 수 있어요",
])
def test_effect_claims_are_rejected(text):
    _, problems = check_reasons(lines(GOOD[0], text, GOOD[2]), "가라앉음", False)
    assert any(p.startswith("effect:") for p in problems), text


@pytest.mark.parametrize("text", [
    "차분함은 그대로 두고 조금 더 밝게 이어 가요",
    "잔잔한 흐름을 담은 조금 더 밝은 곡이에요",
    "가라앉은 마음에 맞춰 어둡고 차분하게 곁에 머물러요",
    "좋은 기분을 편안하게 이어 주는 곡이에요",
    "어둡고 힘찬 곡으로 먼저 마음을 맞춰요",
    "비슷한 분위기를 유지하며 기운을 조금씩 내려놓아요",
])
def test_describing_the_song_is_not_an_effect_claim(text):
    _, problems = check_reasons(lines(GOOD[0], text, GOOD[2]), "가라앉음", False)
    assert not any(p.startswith("effect:") for p in problems), text
