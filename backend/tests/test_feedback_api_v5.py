
"""v5 반응 API의 독립 테스트."""

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.feedback.router import router


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 실제 MoodWave DB 대신 별도 임시 DB를 사용합니다.
    db_path = tmp_path / "feedback_v5_test.db"
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(db_path))

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(
        """
        CREATE TABLE tb_record (
            record_id INTEGER PRIMARY KEY
        );

        CREATE TABLE tb_record_song (
            record_song_id INTEGER PRIMARY KEY,
            record_id INTEGER NOT NULL
                REFERENCES tb_record(record_id)
                ON DELETE CASCADE,
            song_id TEXT NOT NULL,
            recommend_order INTEGER NOT NULL
                CHECK (recommend_order BETWEEN 1 AND 3),
            is_liked INTEGER NOT NULL DEFAULT 0
                CHECK (is_liked IN (0, 1)),
            is_skipped INTEGER NOT NULL DEFAULT 0
                CHECK (is_skipped IN (0, 1)),
            is_completed INTEGER NOT NULL DEFAULT 0
                CHECK (is_completed IN (0, 1)),
            is_engraved INTEGER NOT NULL DEFAULT 0
                CHECK (is_engraved IN (0, 1)),
            UNIQUE (record_id, recommend_order),
            CHECK (NOT (is_skipped = 1 AND is_completed = 1)),
            CHECK (is_engraved = 0 OR is_liked = 1)
        );

        INSERT INTO tb_record (record_id) VALUES (1);

        INSERT INTO tb_record_song
            (record_id, song_id, recommend_order)
        VALUES (1, 'deam_1146', 1);
        """
    )
    con.close()

    # 기존 앱의 DB 초기화와 분리하여 반응 라우터만 검사합니다.
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as api:
        yield api


def test_like_skip_and_read(client):
    # 좋아요 저장
    result = client.put(
        "/api/records/1/songs/1/feedback",
        json={"reaction": "like"},
    )
    assert result.status_code == 200
    assert result.json()["saved"] is True

    # 좋아요 및 LP 새김 확인
    result = client.get("/api/records/1/feedback")
    assert result.status_code == 200
    assert result.json()["songs"][0]["reaction"] == "like"
    assert result.json()["songs"][0]["is_engraved"] is True

    # 건너뛰기로 변경
    result = client.put(
        "/api/records/1/songs/1/feedback",
        json={"reaction": "skip"},
    )
    assert result.status_code == 200

    result = client.get("/api/records/1/feedback")
    song = result.json()["songs"][0]

    assert song["reaction"] == "skip"
    assert song["is_completed"] is False
    assert song["is_engraved"] is False

    # 같은 반응을 다시 보내도 오류가 없어야 합니다.
    result = client.put(
        "/api/records/1/songs/1/feedback",
        json={"reaction": "skip"},
    )
    assert result.status_code == 200


def test_validation_and_not_found(client):
    # 잘못된 반응값
    assert client.put(
        "/api/records/1/songs/1/feedback",
        json={"reaction": "unknown"},
    ).status_code == 422

    # 잘못된 추천 순서
    assert client.put(
        "/api/records/1/songs/4/feedback",
        json={"reaction": "like"},
    ).status_code == 422

    # 존재하지 않는 추천곡
    assert client.put(
        "/api/records/1/songs/2/feedback",
        json={"reaction": "like"},
    ).status_code == 404

    # 존재하지 않는 기록
    assert client.get(
        "/api/records/999/feedback"
    ).status_code == 404
