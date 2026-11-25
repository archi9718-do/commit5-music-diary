"""추천 이유 에이전트 시험. 가짜 클라이언트만 쓰고 실제 Claude API는 부르지 않습니다."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent.service import write_reasons

GOOD = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]
FACTS = {
    "today": {"confirmed_emotion": "가라앉음", "taste_side": None},
    "songs": [
        {"recommend_order": 1, "song_id": "deam_2", "step": "맞추기", "brightness": 0.2, "energy": 0.3},
        {"recommend_order": 2, "song_id": "deam_3", "step": "조금 밝게", "brightness": 0.45, "energy": 0.32},
        {"recommend_order": 3, "song_id": "deam_4", "step": "더 밝게", "brightness": 0.7, "energy": 0.35},
    ],
    "recent_moods": [],
}


class FakeClient:
    """client.with_options(...).beta.messages.create(**kw) 모양만 흉내 냅니다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.timeouts = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **options):
        self.timeouts.append(options.get("timeout"))
        return self

    def _create(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs, ensure_ascii=False, default=str)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def tool_use(name, tool_id=None):
    block = SimpleNamespace(type="tool_use", id=tool_id or f"tu_{name}", name=name, input={})
    return SimpleNamespace(stop_reason="tool_use", content=[block])


def final_text(text):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def final_json(texts):
    body = {"reasons": [{"recommend_order": i, "text": t} for i, t in enumerate(texts, 1)]}
    return final_text(json.dumps(body, ensure_ascii=False))


def test_tool_loop_then_valid_json_returns_texts():
    client = FakeClient([tool_use("get_today"), tool_use("get_songs"), final_json(GOOD)])
    result = write_reasons(FACTS, client=client)
    assert result["texts"] == GOOD and result["stop"] == "ok"
    assert result["tool_calls"] == ["get_today", "get_songs"]
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_get_today"
    assert json.loads(tool_result["content"]) == FACTS["today"]
    # song_id는 Claude에 보내지 않음 (건호 리뷰 #27: 안내에 적은 항목만 보냄)
    sent = client.calls[2]["messages"][-1]["content"][0]["content"]
    assert "song_id" not in sent and "deam_" not in sent
    assert json.loads(sent) == [{k: v for k, v in song.items() if k != "song_id"} for song in FACTS["songs"]]


def test_request_never_contains_diary_text():
    facts = {**FACTS, "today": {**FACTS["today"]}}
    client = FakeClient([tool_use("get_today"), tool_use("get_songs"), tool_use("get_recent_moods"), final_json(GOOD)])
    write_reasons(facts, client=client)
    assert "record_text" not in json.dumps(client.calls, ensure_ascii=False)


def test_request_settings():
    client = FakeClient([final_json(GOOD)])
    write_reasons(FACTS, client=client)
    kw = client.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["effort"] == "low"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert {t["name"] for t in kw["tools"]} == {"get_today", "get_songs", "get_recent_moods"}
    assert all(t["strict"] and t["input_schema"]["properties"] == {} for t in kw["tools"])


def test_system_prompt_is_fixed_across_calls():
    client = FakeClient([tool_use("get_songs"), final_json(GOOD)])
    write_reasons(FACTS, client=client)
    assert client.calls[0]["system"] == client.calls[1]["system"]


def test_each_call_gets_remaining_time_within_deadline():
    client = FakeClient([tool_use("get_songs"), final_json(GOOD)])
    write_reasons(FACTS, client=client)
    assert len(client.timeouts) == 2 and all(0 < t <= 10.0 for t in client.timeouts)
    assert client.timeouts[1] <= client.timeouts[0]


def test_too_many_turns_gives_none():
    client = FakeClient([tool_use("get_today")] * 5)
    result = write_reasons(FACTS, client=client)
    assert result["texts"] is None and result["stop"] == "max_turns" and len(client.calls) == 4


@pytest.mark.parametrize(("responses", "stop"), [
    ([SimpleNamespace(stop_reason="refusal", content=[])], "refusal"),
    ([SimpleNamespace(stop_reason="max_tokens", content=[])], "bad_json"),
    ([final_text("not json")], "bad_json"),
    ([final_text('{"reasons": "x"}')], "checker"),
    ([final_json(["신나는 리듬으로 기분을 바꿔 보아요.", *GOOD[1:]])], "checker"),
])
def test_failures_give_none(responses, stop):
    result = write_reasons(FACTS, client=FakeClient(responses))
    assert result["texts"] is None and result["stop"] == stop


def test_checker_problems_are_reported():
    result = write_reasons(FACTS, client=FakeClient([final_json(["신나는 리듬으로 기분을 바꿔 보아요.", *GOOD[1:]])]))
    assert "emotion:신나" in result["problems"]


def test_exception_gives_none():
    result = write_reasons(FACTS, client=FakeClient([ConnectionError("offline")]))
    assert result["texts"] is None and result["stop"] == "error:ConnectionError"


def test_unknown_tool_name_returns_error_result_not_crash():
    client = FakeClient([tool_use("delete_everything"), final_json(GOOD)])
    result = write_reasons(FACTS, client=client)
    assert result["texts"] == GOOD
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_recent_mood_word_allowed_only_with_history():
    texts = ["요즘 무거웠던 마음처럼 잔잔하게 시작해요.", *GOOD[1:]]
    assert write_reasons(FACTS, client=FakeClient([final_json(texts)]))["stop"] == "checker"
    facts = {**FACTS, "recent_moods": [{"date": "2026-11-23", "emotion": "가라앉음"}]}
    assert write_reasons(facts, client=FakeClient([final_json(texts)]))["texts"] == texts


def test_usage_is_summed_across_calls():
    first, last = tool_use("get_songs"), final_json(GOOD)
    first.usage = SimpleNamespace(input_tokens=100, output_tokens=20)
    last.usage = SimpleNamespace(input_tokens=150, output_tokens=60)
    result = write_reasons(FACTS, client=FakeClient([first, last]))
    assert result["usage"] == {"input_tokens": 250, "output_tokens": 80}


def test_default_client_is_created_once_and_reused(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    from ai.agent import service

    made = []

    def factory(**kwargs):
        made.append(kwargs)
        return FakeClient([final_json(GOOD), final_json(GOOD)])

    monkeypatch.setattr(service, "_client", None)
    monkeypatch.setattr(anthropic, "Anthropic", factory)
    assert service.write_reasons(FACTS)["texts"] == GOOD
    assert service.write_reasons(FACTS)["texts"] == GOOD
    assert len(made) == 1  # 연결을 다시 맺지 않도록 같은 클라이언트를 다시 씀


class WarmClient:
    def __init__(self, error=None):
        self.error, self.retrieved = error, []
        self.models = SimpleNamespace(retrieve=self._retrieve)

    def with_options(self, **options):
        return self

    def _retrieve(self, model):
        self.retrieved.append(model)
        if self.error:
            raise self.error


def test_warm_up_opens_connection_without_tokens(monkeypatch):
    from ai.agent import service

    client = WarmClient()
    monkeypatch.setattr(service, "_client", client)
    monkeypatch.setattr(service, "ready", lambda: True)
    service.warm_up()
    assert client.retrieved == ["claude-opus-5-5"]  # 모델 정보 조회는 토큰을 쓰지 않음


def test_warm_up_never_raises(monkeypatch):
    from ai.agent import service

    monkeypatch.setattr(service, "_client", WarmClient(error=ConnectionError("offline")))
    monkeypatch.setattr(service, "ready", lambda: True)
    service.warm_up()  # 시연장 인터넷이 끊겨도 서버는 켜져야 함


def test_warm_up_skipped_without_key(monkeypatch):
    from ai.agent import service

    client = WarmClient()
    monkeypatch.setattr(service, "_client", client)
    monkeypatch.setattr(service, "ready", lambda: False)
    service.warm_up()
    assert client.retrieved == []


def test_direction_claim_is_checked_against_tool_songs():
    texts = [GOOD[0], "에너지를 낮춰 더 차분하게 이어가요.", GOOD[2]]  # FACTS 2번 곡은 에너지가 0.30→0.32로 오름
    result = write_reasons(FACTS, client=FakeClient([final_json(texts)]))
    assert result["stop"] == "checker" and "direction:에너지" in result["problems"]
