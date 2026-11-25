# rules.py
# 추천 이유 에이전트의 규칙: 위험 표현, 템플릿 문장, 검사기.
# LLM 문장은 check_reasons()를 통과해야만 사용자에게 보입니다. 통과 못 하면 template_reasons()를 씁니다.
# 목록 값은 설계 문서(2026-11-24-recommendation-reason-agent-design.md) 12절의 초안입니다. 상현이 고칩니다.
import re
import unicodedata

# frontend/src/domain.js의 SIGNALS와 같은 목록. 바꾸면 양쪽을 함께 바꾸고
# backend/tests/fixtures/risk_sentences.json으로 두 쪽 시험을 모두 돌립니다.
RISK_PATTERNS = tuple(re.compile(p) for p in (
    r"죽고\s*싶", r"죽어\s*버리고\s*싶", r"살고\s*싶지\s*않", r"목숨을\s*끊",
    r"자해(?:하|를|할|했)", r"자살(?:하|할|을|하고|해야)", r"스스로를\s*해(?:치|칠|쳤)",
    r"자해\s*충동", r"자살\s*생각",
))

LINE_PATTERN = re.compile(r"^[가-힣 .,!?·]+$")  # 한글·띄어쓰기·문장부호만: 숫자·영문·이모지·따옴표 막음
END_PATTERN = re.compile(r"요\.?$")
MIN_LEN, MAX_LEN = 15, 45

FORBIDDEN = (
    "우울증", "공황", "장애", "치료", "진단", "증상", "상담",  # 진단·병명
    "괜찮아질", "나아질", "반드시", "분명히", "틀림없이",  # 약속·단정
    "힘내", "해야", "하세요",  # 명령·훈계
    "친구", "가족", "회사", "학교", "시험",  # 다른 사람·일기 내용 추측
)
# 확정 감정이 아닌 감정의 단어가 나오면 탈락 (도구 결과와 다른 감정을 지어냄)
EMOTION_WORDS = {
    "좋음": ("신나", "기쁜", "기뻐", "행복", "들뜬", "설레"),
    "무난함": ("평범", "무난"),
    "가라앉음": ("슬픈", "슬퍼", "우울", "외로", "눈물"),
    "예민함": ("화나", "짜증", "불안", "초조"),
}
# 도구가 곡 정보를 주지 않으므로 악기·장르·가수 언급은 지어낸 내용
SONG_WORDS = ("피아노", "기타", "드럼", "신스", "보컬", "가사", "장르", "재즈", "힙합", "발라드", "아티스트", "가수", "제목")
RECENT_WORDS = ("요즘", "며칠", "이번 주", "최근")  # 최근 7일 기록이 없으면 언급 금지
# 2·3번째 줄의 "앞 곡보다 어떻게" 말은 실제 밝기·에너지 변화와 맞아야 함 (11/24 건호 리뷰: 낮아졌는데 "더 밝고 힘찬"이 통과)
# 비교하는 말만 셈: "잔잔한", "차분함은 그대로"처럼 상태를 말하는 표현은 방향 주장이 아님
DIRECTION_WORDS = {
    ("brightness", "밝기", +1): ("더 밝", "밝게", "밝아", "밝기를 올", "밝기를 높"),
    ("brightness", "밝기", -1): ("더 어둡", "어둡게", "밝기를 낮", "덜 밝"),
    ("energy", "에너지", +1): ("더 힘", "힘찬", "힘차", "더 활기", "활기차게", "더 신나", "에너지를 올", "에너지를 높",
                               "기운을 올", "끌어올"),
    ("energy", "에너지", -1): ("더 차분", "더 잔잔", "에너지를 낮", "에너지를 줄", "기운을 내려", "기운을 낮", "낮춰",
                               "가라앉혀", "차분해지", "차분해져", "차분해진", "덜 힘", "덜 활기"),
}

TEMPLATES = {
    ("좋음", "비슷한 분위기 1"): "지금의 밝은 기분과 닮은 곡으로 시작해요.",
    ("좋음", "비슷한 분위기 2"): "비슷한 밝기로 좋은 기분을 이어가요.",
    ("좋음", "비슷한 분위기 3"): "같은 분위기로 편안하게 마무리해요.",
    ("무난함", "비슷한 분위기 1"): "지금처럼 고른 분위기의 곡으로 시작해요.",
    ("무난함", "비슷한 분위기 2"): "비슷한 흐름으로 편하게 이어가요.",
    ("무난함", "비슷한 분위기 3"): "잔잔한 분위기로 하루를 마무리해요.",
    ("가라앉음", "맞추기"): "지금 마음처럼 낮고 잔잔한 곡으로 시작해요.",
    ("가라앉음", "조금 밝게"): "밝기를 조금 올려 천천히 이어가요.",
    ("가라앉음", "더 밝게"): "한결 밝은 곡으로 오늘을 마무리해요.",
    ("예민함", "맞추기"): "지금의 높은 긴장과 닮은 곡으로 시작해요.",
    ("예민함", "에너지 낮추기"): "에너지를 낮춘 곡으로 숨을 고르게 해요.",
    ("예민함", "차분하고 조금 밝게"): "차분하고 조금 밝은 곡으로 마무리해요.",
}
# 2·3번째 템플릿이 앞 곡과 비교해 주장하는 것: 1=올라감, -1=내려감, 0=비슷함. 실제 점수와 안 맞으면 GENERIC_TEMPLATE
# 템플릿 문구를 바꾸면 여기도 함께 바꿉니다.
TEMPLATE_CLAIMS = {
    ("좋음", "비슷한 분위기 2"): {"brightness": 0},
    ("좋음", "비슷한 분위기 3"): {"brightness": 0, "energy": 0},
    ("무난함", "비슷한 분위기 2"): {"brightness": 0, "energy": 0},
    ("무난함", "비슷한 분위기 3"): {"brightness": 0, "energy": 0},
    ("가라앉음", "조금 밝게"): {"brightness": 1},
    ("가라앉음", "더 밝게"): {"brightness": 1},
    ("예민함", "에너지 낮추기"): {"energy": -1},
    ("예민함", "차분하고 조금 밝게"): {"brightness": 1, "energy": -1},
}
# ponytail: "비슷함" 기준 0.1은 임시값(목표끼리의 차이는 최대 0.05). 실제 DEAM 점수표로 다시 정하기
SIMILAR_RANGE = 0.1
GENERIC_TEMPLATE = "오늘 고른 기분에 맞춰 고른 곡이에요."


def is_risk(text: str | None) -> bool:
    """기록 글에 위험 표현이 있으면 True. 사진만 기록해 글이 없으면 False."""
    if not text:
        return False
    normalized = unicodedata.normalize("NFC", text).strip()
    return any(pattern.search(normalized) for pattern in RISK_PATTERNS)


def template_reasons(emotion: str, songs: list[dict]) -> list[str]:
    """추천 순서대로 놓인 곡마다 한 줄. 앞 곡과 비교한 말이 실제 점수와 안 맞으면 비교 없는 문장."""
    texts = []
    for i, song in enumerate(songs):
        key = (emotion, song["step"])
        text = TEMPLATES.get(key, GENERIC_TEMPLATE)
        if i > 0:
            for score, sign in TEMPLATE_CLAIMS.get(key, {}).items():
                change = song[score] - songs[i - 1][score]
                if abs(change) > SIMILAR_RANGE if sign == 0 else change * sign <= 0:
                    text = GENERIC_TEMPLATE
        texts.append(text)
    return texts


def check_reasons(
    reasons: list, emotion: str, has_recent: bool, songs: list[dict] | None = None,
) -> tuple[list[str], list[str]]:
    """(다듬은 문장 3개 또는 [], 문제 코드 목록). 평가 보고를 위해 문제를 모두 모읍니다.

    songs(곡 3개의 brightness·energy)를 주면 2·3번째 줄의 비교 표현이 실제 변화와 맞는지도 봅니다.
    """
    problems: list[str] = []

    def add(code: str) -> None:
        if code not in problems:
            problems.append(code)

    if not isinstance(reasons, list) or not all(isinstance(r, dict) for r in reasons):
        return [], ["format"]
    if sorted(r.get("recommend_order") for r in reasons if isinstance(r.get("recommend_order"), int)) != [1, 2, 3] \
            or len(reasons) != 3:
        add("format")

    texts = []
    for reason in sorted(reasons, key=lambda r: r.get("recommend_order") if isinstance(r.get("recommend_order"), int) else 0):
        text = reason.get("text")
        text = text.strip() if isinstance(text, str) else ""
        texts.append(text)
        if not (LINE_PATTERN.match(text) and END_PATTERN.search(text) and MIN_LEN <= len(text) <= MAX_LEN):
            add("format")
        for word in FORBIDDEN:
            if word in text:
                add(f"forbidden:{word}")
        for other, words in EMOTION_WORDS.items():
            if other != emotion:
                for word in words:
                    if word in text:
                        add(f"emotion:{word}")
        for word in SONG_WORDS:
            if word in text:
                add(f"song:{word}")
        if not has_recent:
            for word in RECENT_WORDS:
                if word in text:
                    add(f"recent:{word}")

    if songs and len(songs) == 3 and len(texts) == 3:
        ordered = sorted(songs, key=lambda song: song["recommend_order"])
        for i in (1, 2):
            for (key, label, sign), words in DIRECTION_WORDS.items():
                change = ordered[i][key] - ordered[i - 1][key]
                if any(word in texts[i] for word in words) and change * sign <= 0:
                    add(f"direction:{label}")

    return ([], problems) if problems else (texts, [])
