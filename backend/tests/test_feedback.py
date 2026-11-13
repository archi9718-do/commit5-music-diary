"""v5 DB(tb_record, tb_record_song) 기준 추천곡 반응·LP 새김·하루 1건 덮어쓰기 시험."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import connect

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """시험마다 새 DB 파일과 시험용 점수표를 씁니다."""
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "feedback_test.db"))
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")


def make_record_with_songs(client: TestClient, emotion: str = "가라앉음") -> int:
    record_id = client.post("/api/records", json={"text": "오늘 좀 지쳤어"}).json()["record_id"]
    res = client.post("/api/recommendations", json={"record_id": record_id, "confirmed_emotion": emotion})
    assert res.status_code == 200
    return record_id


def feedback(client: TestClient, record_id: int, order: int, **body):
    return client.patch(f"/api/records/{record_id}/songs/{order}", json=body)


def test_like_skip_complete_and_engrave_only_liked_songs():
    with TestClient(main.app) as client:
        record_id = make_record_with_songs(client)

        # 1번 곡: 좋아요 누른 뒤 건너뜀 / 2·3번 곡: 끝까지 들음
        res = feedback(client, record_id, 1, is_liked=True)
        assert res.status_code == 200
        assert res.json()["is_liked"] is True
        res = feedback(client, record_id, 1, is_skipped=True)
        assert res.json()["is_skipped"] is True
        assert res.json()["is_liked"] is True  # 보내지 않은 좋아요 값은 그대로 유지
        assert feedback(client, record_id, 2, is_completed=True).status_code == 200
        assert feedback(client, record_id, 3, is_completed=True).status_code == 200

        lp = client.get(f"/api/records/{record_id}/lp").json()
        assert [s["recommend_order"] for s in lp["songs"]] == [1, 2, 3]
        assert [s["is_completed"] for s in lp["songs"]] == [False, True, True]
        assert {"song_id", "brightness", "energy", "step", "title", "artist"} <= set(lp["songs"][0])

        # LP 새김: 좋아요 곡(1번)만, 여러 번 불러도 같은 결과
        for _ in range(2):
            engraved = client.post(f"/api/records/{record_id}/engrave")
            assert engraved.status_code == 200
            assert [s["is_engraved"] for s in engraved.json()] == [True, False, False]

        # 좋아요 취소 → 새김도 취소
        res = feedback(client, record_id, 1, is_liked=False)
        assert res.json()["is_engraved"] is False


def test_feedback_errors():
    with TestClient(main.app) as client:
        record_id = make_record_with_songs(client)
        assert feedback(client, 9999, 1, is_liked=True).status_code == 404
        assert feedback(client, record_id, 4, is_liked=True).status_code == 422  # 순서는 1~3
        assert feedback(client, record_id, 1).status_code == 422  # 아무 항목도 안 보냄
        assert client.post("/api/records/9999/engrave").status_code == 404

        # 건너뛴 곡을 완청으로 표시할 수 없음
        assert feedback(client, record_id, 2, is_skipped=True).status_code == 200
        assert feedback(client, record_id, 2, is_completed=True).status_code == 409
        assert feedback(client, record_id, 3, is_skipped=True, is_completed=True).status_code == 409


def test_same_day_record_is_overwritten_but_question_state_is_kept():
    with TestClient(main.app) as client:
        record_id = make_record_with_songs(client)
        assert feedback(client, record_id, 1, is_liked=True).status_code == 200

        # 감상 후 질문을 이미 띄우고 답했다고 가정
        con = connect()
        with con:
            con.execute(
                """UPDATE tb_record SET mood_asked_at = CURRENT_TIMESTAMP, mood_after = '그대로예요'
                   WHERE record_id = ?""", (record_id,))
        con.close()

        # 같은 날 다시 기록 → 같은 ID, 추천곡과 반응은 지워지고 질문 상태는 유지
        again = client.post("/api/records", json={"text": "다시 써 볼게"}).json()["record_id"]
        assert again == record_id
        lp = client.get(f"/api/records/{record_id}/lp").json()
        assert lp["text"] == "다시 써 볼게"
        assert lp["confirmed_emotion"] is None
        assert lp["songs"] == []

        con = connect()
        row = con.execute(
            "SELECT mood_after, mood_asked_at FROM tb_record WHERE record_id = ?", (record_id,)
        ).fetchone()
        count = con.execute("SELECT COUNT(*) FROM tb_record").fetchone()[0]
        con.close()
        assert row["mood_after"] == "그대로예요"
        assert row["mood_asked_at"] is not None
        assert count == 1


def test_recommended_songs_are_registered_in_tb_song():
    with TestClient(main.app) as client:
        record_id = make_record_with_songs(client, emotion="예민함")
        con = connect()
        rows = con.execute(
            """SELECT s.dataset, s.original_id FROM tb_record_song rs
               JOIN tb_song s ON s.song_id = rs.song_id WHERE rs.record_id = ?""", (record_id,)
        ).fetchall()
        con.close()
        assert len(rows) == 3
        assert all(r["dataset"] == "DEAM" and r["original_id"] for r in rows)
