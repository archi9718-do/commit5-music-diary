from contextlib import closing
from sqlite3 import Connection, Row

from fastapi import APIRouter, HTTPException, Path

from .db import connect
from .schemas import (
    MoodAfterState,
    MoodAfterUpdate,
    MoodQuestionState,
    PostListeningState,
)

router = APIRouter(prefix="/api/records", tags=["감상 후 기분"])


def _read_record(con: Connection, record_id: int) -> Row:
    record = con.execute(
        """SELECT r.record_id, r.emotion_final, r.mood_after,
                  strftime('%Y-%m-%dT%H:%M:%SZ', r.flow_ended_at) AS flow_ended_at,
                  strftime('%Y-%m-%dT%H:%M:%SZ', r.mood_asked_at) AS mood_asked_at,
                  COUNT(s.recommend_order) AS song_count,
                  COUNT(DISTINCT CASE WHEN s.is_completed = 1 THEN s.song_id END) AS completed_song_count
           FROM tb_record AS r
           LEFT JOIN tb_record_song AS s ON s.record_id = r.record_id
           WHERE r.record_id = ?
           GROUP BY r.record_id""",
        (record_id,),
    ).fetchone()
    if record is None:
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
    return record


def _should_ask(record: Row) -> bool:
    return (
        record["emotion_final"] in {"가라앉음", "예민함"}
        and record["flow_ended_at"] is not None
        and record["completed_song_count"] >= 2
        and record["mood_asked_at"] is None
        and record["mood_after"] is None
    )


def _state(record: Row) -> PostListeningState:
    return PostListeningState(**dict(record), should_ask_mood=_should_ask(record))


@router.get("/{record_id}/post-listening", response_model=PostListeningState)
def get_post_listening(record_id: int = Path(gt=0)):
    with closing(connect()) as con:
        return _state(_read_record(con, record_id))


@router.post("/{record_id}/flow/end", response_model=PostListeningState)
def end_listening(record_id: int = Path(gt=0)):
    with closing(connect()) as con, con:
        con.execute("BEGIN IMMEDIATE")
        record = _read_record(con, record_id)
        if record["emotion_final"] is None or record["song_count"] != 3:
            raise HTTPException(status_code=409, detail="감정을 확정하고 3곡을 추천받은 뒤 감상을 마칠 수 있습니다.")
        if record["flow_ended_at"] is None:
            con.execute(
                "UPDATE tb_record SET flow_ended_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE record_id = ?",
                (record_id,),
            )
            record = _read_record(con, record_id)
        return _state(record)


@router.post("/{record_id}/mood-question", response_model=MoodQuestionState)
def allow_mood_question(record_id: int = Path(gt=0)):
    with closing(connect()) as con, con:
        con.execute("BEGIN IMMEDIATE")
        record = _read_record(con, record_id)
        if record["mood_asked_at"] is not None:
            return MoodQuestionState(**dict(record), show_question=False)
        if not _should_ask(record):
            raise HTTPException(status_code=409, detail="감상 후 기분 질문을 표시할 조건을 충족하지 않았습니다.")
        con.execute(
            "UPDATE tb_record SET mood_asked_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE record_id = ?",
            (record_id,),
        )
        return MoodQuestionState(**dict(_read_record(con, record_id)), show_question=True)


@router.patch("/{record_id}/mood-after", response_model=MoodAfterState)
def save_mood_after(payload: MoodAfterUpdate, record_id: int = Path(gt=0)):
    with closing(connect()) as con, con:
        con.execute("BEGIN IMMEDIATE")
        record = _read_record(con, record_id)
        if record["mood_asked_at"] is None:
            raise HTTPException(status_code=409, detail="감상 후 기분 질문이 표시된 뒤에 응답할 수 있습니다.")
        if record["mood_after"] is not None:
            if record["mood_after"] != payload.mood_after:
                raise HTTPException(status_code=409, detail="이미 저장된 감상 후 기분은 변경할 수 없습니다.")
            return MoodAfterState(**dict(record))
        con.execute("UPDATE tb_record SET mood_after = ? WHERE record_id = ?", (payload.mood_after, record_id))
        return MoodAfterState(**(dict(record) | {"mood_after": payload.mood_after}))
