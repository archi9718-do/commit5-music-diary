"""참여자 코드(X-Participant) 시험: 12/7 평가에서 시연 기기 한 대를 돌려 쓸 때 참여자별로 기록을 나눕니다."""

from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_analyze import FakeEmotionService
from test_voice import FakeSttService

from app import db, main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "participant.db"))
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")
    with TestClient(main.app) as test_client:
        yield test_client


def as_(code):
    return {"X-Participant": code} if code else {}


def email_of(record_id):
    with closing(db.connect()) as con:
        return con.execute(
            "SELECT u.email FROM tb_record r JOIN tb_user u ON u.user_id = r.user_id WHERE r.record_id = ?",
            (record_id,),
        ).fetchone()[0]


def count_records():
    with closing(db.connect()) as con:
        return con.execute("SELECT COUNT(*) FROM tb_record").fetchone()[0]


def new_record(client, code, text="오늘 기록"):
    return client.post("/api/records", json={"text": text}, headers=as_(code)).json()["record_id"]


def recommend(client, code, record_id):
    return client.post("/api/recommendations", json={"record_id": record_id, "confirmed_emotion": "가라앉음"},
                       headers=as_(code))


def test_no_header_uses_demo_user(client):
    assert email_of(new_record(client, None)) == "demo@moodwave.local"


def test_two_participants_same_day_keep_both_records(client):
    a, b = new_record(client, "AAAA"), new_record(client, "BBBB")
    assert a != b
    assert email_of(a) == "participant-AAAA@moodwave.local"
    assert email_of(b) == "participant-BBBB@moodwave.local"
    assert new_record(client, "AAAA", "다시") == a  # 같은 참여자는 같은 날 덮어쓰기 규칙 그대로


@pytest.mark.parametrize("code", ["k7qm", "ABCDE", "AB-1", ""])
def test_bad_participant_code_is_422_and_saves_nothing(client, code):
    response = client.post("/api/records", json={"text": "a"}, headers={"X-Participant": code})
    assert response.status_code == 422
    assert count_records() == 0


def test_analyze_and_voice_use_participant(client, monkeypatch):
    monkeypatch.setattr(main, "emotion_service", FakeEmotionService())
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    monkeypatch.setitem(main.EMOTION_STATUS, "ready", True)
    monkeypatch.setitem(main.STT_STATUS, "ready", True)
    analyzed = client.post("/api/records/analyze", json={"text": "오늘 좀 지쳤어"}, headers=as_("CCCC"))
    assert analyzed.status_code == 201 and email_of(analyzed.json()["record_id"]) == "participant-CCCC@moodwave.local"
    voiced = client.post("/api/records/voice", content=b"fake",
                         headers={"Content-Type": "audio/webm", "X-Participant": "DDDD"})
    assert voiced.status_code == 201 and email_of(voiced.json()["record_id"]) == "participant-DDDD@moodwave.local"


def test_cors_preflight_allows_participant_header(client):
    response = client.options("/api/records", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-participant",
    })
    assert response.status_code == 200
    assert "x-participant" in response.headers["access-control-allow-headers"].lower()


def test_owner_can_use_own_record(client):
    record_id = new_record(client, "AAAA")
    assert recommend(client, "AAAA", record_id).status_code == 200
    assert client.get(f"/api/records/{record_id}/lp", headers=as_("AAAA")).status_code == 200


@pytest.mark.parametrize("other", ["BBBB", None])
def test_other_participant_cannot_see_or_change_record(client, other):
    record_id = new_record(client, "AAAA")
    assert recommend(client, "AAAA", record_id).status_code == 200
    path = f"/api/records/{record_id}"
    headers = as_(other)
    assert client.get(f"{path}/lp", headers=headers).status_code == 404
    assert recommend(client, other, record_id).status_code == 404
    assert client.patch(f"{path}/songs/1", json={"is_liked": True}, headers=headers).status_code == 404
    assert client.post(f"{path}/engrave", json={"recommend_orders": []}, headers=headers).status_code == 404
    assert client.get(f"{path}/post-listening", headers=headers).status_code == 404
    emotion = {"record_id": record_id, "text": "남의 기록", "emotion": "좋음", "confidence": "높음",
               "probs": {"좋음": 0.7, "무난함": 0.1, "가라앉음": 0.1, "예민함": 0.1}}
    assert client.post("/api/emotions", json=emotion, headers=headers).status_code == 404
    # 주인의 기록은 그대로
    lp = client.get(f"{path}/lp", headers=as_("AAAA")).json()
    assert lp["text"] == "오늘 기록" and not any(song["is_liked"] for song in lp["songs"])


def test_recent_song_exclusion_is_per_participant(client):
    with closing(db.connect()) as con, con:
        assert db.get_user_id(con, "AAAA") != db.get_user_id(con, "BBBB")
        assert db.get_user_id(con, "AAAA") == db.get_user_id(con, "AAAA")
        assert db.get_user_id(con, None) == db.get_demo_user_id(con)
