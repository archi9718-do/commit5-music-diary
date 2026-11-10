import os
import tempfile
from pathlib import Path

# 앱을 import하기 전에 테스트 DB 파일 위치를 지정합니다.
TEST_DIR = tempfile.TemporaryDirectory()
os.environ["MOODWAVE_DB_PATH"] = str(Path(TEST_DIR.name) / "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


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
        assert all(song["song_id"].startswith("mock_") for song in songs)

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
