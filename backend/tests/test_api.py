import os
import tempfile
from pathlib import Path

# 앱을 import하기 전에 테스트 DB 파일 위치를 지정합니다.
TEST_DIR = tempfile.TemporaryDirectory()
os.environ["MOODWAVE_DB_PATH"] = str(Path(TEST_DIR.name) / "test.db")

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app


@pytest.fixture(autouse=True)
def setup_recommendation_fixture(monkeypatch):
    """실제 연구용 점수 CSV 대신 인공 테스트 점수만 사용해 API를 검증합니다."""
    csv_path = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(csv_path))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")


def test_record_emotion_recommendation_lp():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200

        created = client.post("/api/records", json={"text": "오늘 좀 지쳤어"})
        assert created.status_code == 201
        record_id = created.json()["record_id"]

        emotion_result = {
            "record_id": record_id,
            "text": "오늘 좀 지쳤어",
            "probs": {"좋음": 0.10, "무난함": 0.15, "가라앉음": 0.62, "예민함": 0.13},
            "emotion": "가라앉음",
            "confidence": "중간",
        }
        accepted = client.post("/api/emotions", json=emotion_result)
        assert accepted.status_code == 200

        recommended = client.post(
            "/api/recommendations",
            json={"record_id": record_id, "confirmed_emotion": "가라앉음"},
        )
        assert recommended.status_code == 200
        songs = recommended.json()["songs"]
        assert len(songs) == 3
        assert [song["step"] for song in songs] == ["맞추기", "조금 밝게", "더 밝게"]
        assert all(song["song_id"].startswith("deam_") for song in songs)

        lp = client.get(f"/api/records/{record_id}/lp")
        assert lp.status_code == 200
        assert len(lp.json()["songs"]) == 3
        assert lp.json()["confirmed_emotion"] == "가라앉음"


def test_missing_record_and_bad_probabilities():
    with TestClient(app) as client:
        assert client.post(
            "/api/recommendations",
            json={"record_id": 9999999, "confirmed_emotion": "무난함"},
        ).status_code == 404
        new_id = client.post("/api/records", json={"text": "테스트"}).json()["record_id"]
        invalid = client.post("/api/emotions", json={
            "record_id": new_id,
            "text": "테스트",
            "probs": {"좋음": 1.0},
            "emotion": "좋음",
            "confidence": "높음",
        })
        assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("days_ago", "same_user", "exclude_recent"),
    [(7, True, True), (8, True, False), (1, False, False)],
)
def test_recommendations_use_only_same_users_previous_week(
    monkeypatch, tmp_path, days_ago, same_user, exclude_recent,
):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "recommendation_history.db"))
    with TestClient(app) as client:
        prior_id = client.post("/api/records", json={"text": "이전 기록"}).json()["record_id"]
        first = client.post(
            "/api/recommendations", json={"record_id": prior_id, "confirmed_emotion": "좋음"},
        )
        assert first.status_code == 200
        prior_songs = {song["song_id"] for song in first.json()["songs"]}

        con = connect()
        try:
            with con:
                con.execute("UPDATE tb_record SET record_date = date(record_date, ?) WHERE record_id = ?",
                            (f"-{days_ago} days", prior_id))
                if not same_user:
                    user_id = con.execute(
                        "INSERT INTO tb_user (email, password_hash) VALUES (?, ?)", ("other@example.test", "test"),
                    ).lastrowid
                    con.execute("UPDATE tb_record SET user_id = ? WHERE record_id = ?", (user_id, prior_id))
        finally:
            con.close()

        record_id = client.post("/api/records", json={"text": "오늘 기록"}).json()["record_id"]
        payload = {"record_id": record_id, "confirmed_emotion": "좋음"}
        response = client.post("/api/recommendations", json=payload)
        assert response.status_code == 200
        songs = response.json()["songs"]
        ids = {song["song_id"] for song in songs}
        assert len(ids) == 3
        if exclude_recent:
            assert ids.isdisjoint(prior_songs)
        else:
            assert ids == prior_songs

        lp = client.get(f"/api/records/{record_id}/lp")
        assert [song["song_id"] for song in lp.json()["songs"]] == [song["song_id"] for song in songs]
        assert client.post("/api/recommendations", json=payload).json()["songs"] == songs
