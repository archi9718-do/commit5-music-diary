"""POST /api/records/{record_id}/reasons 시험. 에이전트는 가짜로 바꿔 끼워 실제 API를 부르지 않습니다."""

from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main, reasons

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"
GOOD = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]
TEMPLATES = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]


class FakeAgent:
    def __init__(self, texts=GOOD, error=None):
        self.texts, self.error, self.facts = texts, error, []

    def __call__(self, facts):
        self.facts.append(facts)
        if self.error:
            raise self.error
        return {"texts": self.texts, "problems": [], "tool_calls": [], "stop": "ok" if self.texts else "checker"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "reasons.db"))
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")
    monkeypatch.setattr(reasons, "agent_ready", lambda: True)
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def agent(monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(reasons, "write_reasons", fake)
    return fake


def recommend(client, text="오늘 좀 지쳤어", emotion="가라앉음"):
    record_id = client.post("/api/records", json={"text": text}).json()["record_id"]
    assert client.post("/api/recommendations", json={"record_id": record_id, "confirmed_emotion": emotion}).status_code == 200
    return record_id


def song_ids(client, record_id):
    return [song["song_id"] for song in client.get(f"/api/records/{record_id}/lp").json()["songs"]]


def test_agent_success(client, agent):
    record_id = recommend(client)
    body = client.post(f"/api/records/{record_id}/reasons").json()
    assert body["source"] == "agent" and body["risk"] is False
    assert [r["text"] for r in body["reasons"]] == GOOD
    assert [r["recommend_order"] for r in body["reasons"]] == [1, 2, 3]
    assert [r["song_id"] for r in body["reasons"]] == song_ids(client, record_id)


def test_agent_receives_facts_without_diary_text(client, agent):
    record_id = recommend(client)
    client.post(f"/api/records/{record_id}/reasons")
    facts = agent.facts[0]
    assert facts["today"] == {"confirmed_emotion": "가라앉음", "taste_side": None}
    assert [s["step"] for s in facts["songs"]] == ["맞추기", "조금 밝게", "더 밝게"]
    assert [s["song_id"] for s in facts["songs"]] == song_ids(client, record_id)
    assert all(0 <= s["brightness"] <= 1 and 0 <= s["energy"] <= 1 for s in facts["songs"])
    assert facts["recent_moods"] == []
    assert "오늘 좀 지쳤어" not in repr(facts)


def test_agent_failure_gives_template(client, monkeypatch):
    monkeypatch.setattr(reasons, "write_reasons", FakeAgent(texts=None))
    body = client.post(f"/api/records/{recommend(client)}/reasons").json()
    assert body["source"] == "template" and [r["text"] for r in body["reasons"]] == TEMPLATES


def test_agent_exception_still_200_template(client, monkeypatch):
    monkeypatch.setattr(reasons, "write_reasons", FakeAgent(error=RuntimeError("boom")))
    response = client.post(f"/api/records/{recommend(client)}/reasons")
    assert response.status_code == 200 and response.json()["source"] == "template"


def test_not_ready_gives_template_without_calling_agent(client, agent, monkeypatch):
    monkeypatch.setattr(reasons, "agent_ready", lambda: False)
    body = client.post(f"/api/records/{recommend(client)}/reasons").json()
    assert body["source"] == "template" and agent.facts == []


def test_risk_text_skips_agent(client, agent):
    body = client.post(f"/api/records/{recommend(client, text='더는 살고 싶지 않아')}/reasons").json()
    assert body["risk"] is True and body["source"] == "template" and agent.facts == []
    assert len(body["reasons"]) == 3


def test_photo_only_record_is_not_risk(client, agent):
    body = client.post(f"/api/records/{recommend(client, text='')}/reasons").json()
    assert body["risk"] is False and body["source"] == "agent"


def test_before_recommendation_is_409(client, agent):
    record_id = client.post("/api/records", json={"text": "추천 전"}).json()["record_id"]
    assert client.post(f"/api/records/{record_id}/reasons").status_code == 409


def test_missing_record_is_404(client, agent):
    assert client.post("/api/records/9999/reasons").status_code == 404


def test_recent_moods_only_same_user_previous_7_days(client, agent):
    record_id = recommend(client)
    with closing(db.connect()) as con, con:
        user_id, today = con.execute(
            "SELECT user_id, record_date FROM tb_record WHERE record_id = ?", (record_id,)
        ).fetchone()
        other = con.execute("INSERT INTO tb_user (email, password_hash) VALUES ('other@example.test', 'x')").lastrowid
        rows = [
            (user_id, "-1 days", "예민함"),  # 남아야 함
            (user_id, "-3 days", None),  # 확정 감정 없음 → 빠짐
            (user_id, "-8 days", "좋음"),  # 7일보다 전 → 빠짐
            (other, "-2 days", "좋음"),  # 다른 사용자 → 빠짐
        ]
        for uid, shift, emotion in rows:
            con.execute(
                "INSERT INTO tb_record (user_id, record_date, emotion_final) VALUES (?, date(?, ?), ?)",
                (uid, today, shift, emotion),
            )
        yesterday = con.execute("SELECT date(?, '-1 days')", (today,)).fetchone()[0]
    client.post(f"/api/records/{record_id}/reasons")
    assert agent.facts[0]["recent_moods"] == [{"date": yesterday, "emotion": "예민함"}]


def test_slow_agent_is_cut_at_deadline(client, monkeypatch):
    import time

    def slow(facts):
        time.sleep(1.0)
        return {"texts": GOOD, "problems": [], "tool_calls": [], "stop": "ok"}

    monkeypatch.setattr(reasons, "write_reasons", slow)
    monkeypatch.setattr(reasons, "DEADLINE_SECONDS", 0.2)
    record_id = recommend(client)
    started = time.perf_counter()
    body = client.post(f"/api/records/{record_id}/reasons").json()
    assert body["source"] == "template" and time.perf_counter() - started < 0.9
