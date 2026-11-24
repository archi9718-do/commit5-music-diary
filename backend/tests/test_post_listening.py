from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "post_listening.db"))
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")
    with TestClient(main.app) as test_client:
        yield test_client


def create_flow(client, emotion, completed):
    record_id = client.post("/api/records", json={"text": "시험 기록"}).json()["record_id"]
    response = client.post("/api/recommendations", json={"record_id": record_id, "confirmed_emotion": emotion})
    assert response.status_code == 200
    path = f"/api/records/{record_id}"
    for order in range(1, completed + 1):
        assert client.patch(f"{path}/songs/{order}", json={"is_completed": True}).status_code == 200
    return record_id, path


@pytest.mark.parametrize("emotion", ["좋음", "무난함", "가라앉음", "예민함"])
@pytest.mark.parametrize("completed", [0, 1, 2, 3])
def test_question_eligibility_after_end(client, emotion, completed):
    record_id, path = create_flow(client, emotion, completed)
    # 예측 감정과 무관하게 확정 감정만 질문 조건에 사용합니다.
    with closing(db.connect()) as con, con:
        predicted = "좋음" if emotion in {"가라앉음", "예민함"} else "가라앉음"
        con.execute("UPDATE tb_record SET emotion_pred = ? WHERE record_id = ?", (predicted, record_id))
    if completed:
        assert client.patch(f"{path}/songs/1", json={"is_completed": True}).status_code == 200
    before = client.get(f"{path}/post-listening").json()
    assert before == {
        "record_id": record_id, "flow_ended_at": None, "completed_song_count": completed,
        "should_ask_mood": False, "mood_asked_at": None, "mood_after": None,
    }
    assert client.get(f"{path}/post-listening").json() == before
    assert client.post(f"{path}/mood-question").status_code == 409
    ended = client.post(f"{path}/flow/end").json()
    assert ended["flow_ended_at"].endswith("Z")
    assert ended["completed_song_count"] == completed
    assert ended["should_ask_mood"] == (emotion in {"가라앉음", "예민함"} and completed >= 2)
    assert ended["mood_asked_at"] is None
    assert client.post(f"{path}/flow/end").json() == ended


@pytest.mark.parametrize("answer", ["조금 나아졌어요", "무응답"])
def test_question_and_answer_are_idempotent_and_preserved(client, monkeypatch, answer):
    monkeypatch.setattr(db, "today_kst", lambda: "2026-11-23")
    record_id, path = create_flow(client, "가라앉음", 2)
    body = {"mood_after": answer}
    assert client.patch(f"{path}/mood-after", json=body).status_code == 409
    assert client.post(f"{path}/flow/end").status_code == 200
    question = client.post(f"{path}/mood-question").json()
    assert question["show_question"] is True
    assert question["mood_asked_at"].endswith("Z")
    assert client.post(f"{path}/mood-question").json() == {**question, "show_question": False}
    assert client.get(f"{path}/post-listening").json()["mood_after"] is None

    # 재기록·재추천 뒤에도 이미 허용된 질문에는 최초 응답을 저장할 수 있습니다.
    repeated_id, _ = create_flow(client, "좋음", 0)
    assert repeated_id == record_id
    state = client.get(f"{path}/post-listening").json()
    assert state["flow_ended_at"] is None
    assert state["mood_asked_at"] == question["mood_asked_at"]
    saved = client.patch(f"{path}/mood-after", json=body)
    assert saved.status_code == 200
    assert saved.json()["mood_after"] == answer
    assert client.patch(f"{path}/mood-after", json=body).json() == saved.json()
    assert client.patch(f"{path}/mood-after", json={"mood_after": "그대로예요"}).status_code == 409
    assert client.get(f"{path}/lp").json()["mood_after"] == answer
    assert create_flow(client, "무난함", 0)[0] == record_id
    with TestClient(main.app) as restarted:
        assert restarted.get(f"{path}/post-listening").json()["mood_after"] == answer
    monkeypatch.setattr(db, "today_kst", lambda: "2026-11-24")
    new_id, new_path = create_flow(client, "가라앉음", 2)
    assert new_id != record_id
    assert client.get(f"{new_path}/post-listening").json()["mood_asked_at"] is None


def test_concurrent_question_and_answer_only_allow_one_first_write(client):
    _, path = create_flow(client, "예민함", 2)
    assert client.post(f"{path}/flow/end").status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        questions = list(pool.map(lambda _: client.post(f"{path}/mood-question"), range(2)))
        assert [event.status_code for event in questions] == [200, 200]
        assert sum(event.json()["show_question"] for event in questions) == 1
        assert len({event.json()["mood_asked_at"] for event in questions}) == 1
        answers = list(pool.map(
            lambda answer: client.patch(f"{path}/mood-after", json={"mood_after": answer}),
            ["그대로예요", "더 무거워졌어요"],
        ))
    assert sorted(event.status_code for event in answers) == [200, 409]
    winner = next(event.json()["mood_after"] for event in answers if event.status_code == 200)
    assert client.get(f"{path}/post-listening").json()["mood_after"] == winner


def test_request_validation_and_missing_record(client):
    record_id = client.post("/api/records", json={"text": "아직 추천 전"}).json()["record_id"]
    path = f"/api/records/{record_id}"
    assert client.post(f"{path}/flow/end").status_code == 409
    for body in ({}, {"mood_after": None}, {"mood_after": "기타"}, {"mood_after": "무응답", "time": "now"}):
        assert client.patch(f"{path}/mood-after", json=body).status_code == 422
    for method, route in [
        ("GET", "post-listening"), ("POST", "flow/end"), ("POST", "mood-question"), ("PATCH", "mood-after"),
    ]:
        kwargs = {"json": {"mood_after": "무응답"}} if method == "PATCH" else {}
        assert client.request(method, f"/api/records/999999/{route}", **kwargs).status_code == 404
        assert client.request(method, f"/api/records/0/{route}", **kwargs).status_code == 422
