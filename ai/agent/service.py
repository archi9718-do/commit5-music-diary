# service.py
# 추천 이유 에이전트의 "입구" 파일. 서버는 ready()와 write_reasons()만 부릅니다.
# Claude가 도구 3개로 오늘의 사실을 확인한 뒤 곡마다 이유 한 줄을 씁니다.
# 일기 원문은 받지도 보내지도 않습니다. 사실(facts)은 서버가 DB에서 모아 넘깁니다.
import json
import logging
import os
import time

if __package__:
    from .rules import check_reasons
else:
    from rules import check_reasons

logger = logging.getLogger("moodwave.agent")

MODEL = "claude-opus-5-5"
MAX_TURNS = 4
DEADLINE_SECONDS = 10.0  # 반복 전체의 시간 상한. 화면은 그동안 단계 이름을 보여 줌
MAX_TOKENS = 4000
_client = None  # 한 번 만들어 다시 씀: 요청마다 새로 만들면 매번 연결을 다시 맺어 첫 호출이 느림(11/24 11.8초)

SYSTEM_PROMPT = """당신은 음악 일기 앱에서 추천곡마다 이유 한 줄을 쓰는 도우미입니다.
도구로 오늘 확정된 감정, 추천된 3곡의 단계와 밝기·에너지, 최근 7일 감정을 확인한 뒤 씁니다.

규칙:
- 곡마다 한국어 한 줄, 15~45자, "요"로 끝나는 부드러운 존댓말
- 도구 결과에 있는 사실만 근거로 씁니다. 도구 결과에 없는 내용은 쓰지 않습니다
- 숫자를 쓰지 않습니다. 밝기·에너지는 "조금 더 밝게", "차분하게"처럼 말로 표현합니다
- 곡 제목, 가수, 악기, 장르를 언급하지 않습니다 (도구가 알려 주지 않습니다)
- 확정된 감정과 다른 감정을 말하지 않습니다
- 2·3번째 곡을 앞 곡과 비교할 때는 get_songs의 밝기·에너지가 실제로 오른 쪽, 내린 쪽만 말합니다 (예: 에너지가 올랐으면 "더 차분하게"라고 쓰지 않음)
- 진단, 병명, 치료, 상담 권유, "괜찮아질 거예요" 같은 약속, "힘내", "~하세요" 같은 명령을 쓰지 않습니다
- 사용자의 하루나 주변 사람을 짐작해 말하지 않습니다
- 최근 7일 기록이 비어 있으면 "요즘", "최근"을 쓰지 않습니다
- 영어, 이모지, 따옴표를 쓰지 않습니다"""

FIRST_MESSAGE = "오늘 추천된 3곡에 대해 곡마다 이유 한 줄을 써 주세요. 도구로 사실을 확인하세요."

_NO_INPUT = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
TOOLS = [
    {"name": "get_today", "description": "오늘 사용자가 확정한 감정과 취향 쪽(없으면 null)을 돌려줍니다.",
     "strict": True, "input_schema": _NO_INPUT},
    {"name": "get_songs", "description": "추천된 3곡의 순서, 단계 이름, 밝기(0~1), 에너지(0~1)를 돌려줍니다.",
     "strict": True, "input_schema": _NO_INPUT},
    {"name": "get_recent_moods", "description": "지난 7일(오늘 제외) 날짜별 확정 감정을 돌려줍니다. 없으면 빈 목록입니다.",
     "strict": True, "input_schema": _NO_INPUT},
]
OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"reasons": {"type": "array", "items": {
            "type": "object",
            "properties": {"recommend_order": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["recommend_order", "text"],
            "additionalProperties": False,
        }}},
        "required": ["reasons"],
        "additionalProperties": False,
    },
}


def ready() -> bool:
    """SDK가 설치돼 있고 키가 있으면 True. 아니면 서버는 템플릿 문장을 씁니다."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _default_client():
    global _client
    if _client is None:
        import anthropic  # SDK가 없어도 이 모듈은 불러올 수 있게 여기서 불러옴

        _client = anthropic.Anthropic(max_retries=1)
    return _client


def warm_up() -> None:
    """서버가 켜질 때 한 번: SDK를 불러오고 연결을 미리 맺어 둠 (11/24 첫 요청 11.2초 → 10초 상한 넘김).

    모델 정보 조회(models.retrieve)는 토큰을 쓰지 않습니다. 실패해도 서버는 켜집니다.
    """
    if not ready():
        return
    try:
        _default_client().with_options(timeout=5.0).models.retrieve(MODEL)
    except Exception as exc:  # noqa: BLE001 - 미리 준비가 실패해도 첫 요청에서 다시 연결하면 됨
        logger.warning("추천 이유 에이전트 미리 연결 실패: %s", type(exc).__name__)


def _tool_results(blocks, facts: dict, called: list[str]) -> list[dict]:
    sources = {"get_today": "today", "get_songs": "songs", "get_recent_moods": "recent_moods"}
    results = []
    for block in blocks:
        called.append(block.name)
        key = sources.get(block.name)
        if key is None:
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": "알 수 없는 도구입니다.",
                            "is_error": True})
        else:
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(facts[key], ensure_ascii=False)})
    return results


def write_reasons(facts: dict, *, client=None) -> dict:
    """{"texts": 3줄 또는 None, "problems": [...], "tool_calls": [...], "stop": "...", "usage": {...}}. 예외를 던지지 않습니다."""
    called: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0}  # 평가 스크립트의 비용 계산용

    def done(stop: str, texts=None, problems=None) -> dict:
        return {"texts": texts, "problems": problems or [], "tool_calls": called, "stop": stop, "usage": usage}

    try:
        if client is None:
            client = _default_client()
        deadline = time.monotonic() + DEADLINE_SECONDS
        messages = [{"role": "user", "content": FIRST_MESSAGE}]
        for _ in range(MAX_TURNS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return done("timeout")
            response = client.with_options(timeout=remaining).beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
                output_config={"effort": "low", "format": OUTPUT_FORMAT},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            for key in usage:
                usage[key] += getattr(getattr(response, "usage", None), key, 0) or 0
            if response.stop_reason == "refusal":
                return done("refusal")
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "tool_use" and tool_blocks:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": _tool_results(tool_blocks, facts, called)})
                continue
            text = next((b.text for b in response.content if b.type == "text"), None)
            try:
                data = json.loads(text) if text else None
            except json.JSONDecodeError:
                data = None
            if not isinstance(data, dict):
                return done("bad_json")
            texts, problems = check_reasons(data.get("reasons"), facts["today"]["confirmed_emotion"],
                                            has_recent=bool(facts["recent_moods"]), songs=facts["songs"])
            return done("ok", texts) if not problems else done("checker", problems=problems)
        return done("max_turns")
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 템플릿으로 대신하므로 이름만 남김
        logger.warning("추천 이유 에이전트 실패: %s", type(exc).__name__)
        return done(f"error:{type(exc).__name__}")
