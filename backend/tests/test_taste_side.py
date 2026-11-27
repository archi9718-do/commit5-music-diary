"""취향 유형 쪽(taste_side) 시험: 추천 요청에서 받고, 추천 계산에 쓰고, 기록에 남깁니다."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "taste.db"))
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")
    with TestClient(main.app) as test_client:
        yield test_client


def new_record(client):
    return client.post("/api/records", json={"text": "오늘 기록"}).json()["record_id"]


def recommend(client, record_id, **extra):
    return client.post("/api/recommendations",
                       json={"record_id": record_id, "confirmed_emotion": "가라앉음", **extra})


def stored_side(record_id):
    with closing(db.connect()) as con:
        return con.execute("SELECT taste_side FROM tb_record WHERE record_id = ?", (record_id,)).fetchone()[0]


def song_rows(record_id):
    with closing(db.connect()) as con:
        return con.execute("SELECT COUNT(*) FROM tb_record_song WHERE record_id = ?", (record_id,)).fetchone()[0]


def steps(response):
    return [song["step"] for song in response.json()["songs"]]


def test_without_taste_side_matches_default_and_stores_null(client):
    rid = new_record(client)
    r = recommend(client, rid)
    assert r.status_code == 200
    assert steps(r) == ["맞추기", "조금 밝게", "더 밝게"]
    assert stored_side(rid) is None


def test_taste_side_changes_songs_and_is_stored(client):
    rid = new_record(client)
    r = recommend(client, rid, taste_side="머무름")
    assert r.status_code == 200
    assert steps(r) == ["맞추기", "곁에 머물기", "잔잔하게 마무리"]
    assert stored_side(rid) == "머무름"


def test_default_side_is_stored_not_null(client):
    rid = new_record(client)
    assert recommend(client, rid, taste_side="위로").status_code == 200
    assert stored_side(rid) == "위로"  # 검사 안 함(NULL)과 기본 쪽 선택을 구분


@pytest.mark.parametrize("side", ["발산", "없는쪽"])
def test_side_not_matching_emotion_is_422(client, side):
    rid = new_record(client)
    assert recommend(client, rid, taste_side=side).status_code == 422
    assert song_rows(rid) == 0


def test_rerecord_same_day_clears_taste_side(client):
    rid = new_record(client)
    recommend(client, rid, taste_side="머무름")
    assert new_record(client) == rid  # 같은 날 덮어쓰기
    assert stored_side(rid) is None


def test_old_db_gets_column_on_startup(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    old_schema = "\n".join(line for line in db.SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
                           if not line.lstrip().startswith("taste_side"))  # 취향 유형 전 schema.sql
    with closing(sqlite3.connect(path)) as con:
        con.executescript(old_schema)
        assert "taste_side" not in {row[1] for row in con.execute("PRAGMA table_info(tb_record)")}
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(path))
    db.init_db()
    with closing(sqlite3.connect(path)) as con:
        assert "taste_side" in {row[1] for row in con.execute("PRAGMA table_info(tb_record)")}
