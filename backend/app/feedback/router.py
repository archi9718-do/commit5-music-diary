
"""추천곡 좋아요·건너뛰기 API."""

from fastapi import APIRouter, HTTPException, Path

from ..db import connect
from ..schemas import SongFeedbackRequest

router = APIRouter(
    prefix="/api/records",
    tags=["음악 반응"],
)


@router.put("/{record_id}/songs/{position}/feedback")
def save_song_feedback(
    payload: SongFeedbackRequest,
    record_id: int = Path(gt=0),
    position: int = Path(ge=1, le=3),
):
    """이미 추천된 곡의 반응을 저장하거나 변경합니다."""

    con = connect()

    try:
        with con:
            if payload.reaction == "like":
                # 좋아요를 누른 곡은 LP에 새길 대상으로 표시합니다.
                cursor = con.execute(
                    """
                    UPDATE tb_record_song
                    SET is_liked = 1,
                        is_skipped = 0,
                        is_engraved = 1
                    WHERE record_id = ?
                      AND recommend_order = ?
                    """,
                    (record_id, position),
                )

            else:
                # 건너뛰기로 변경하면 완청·LP 새김도 해제합니다.
                cursor = con.execute(
                    """
                    UPDATE tb_record_song
                    SET is_liked = 0,
                        is_skipped = 1,
                        is_completed = 0,
                        is_engraved = 0
                    WHERE record_id = ?
                      AND recommend_order = ?
                    """,
                    (record_id, position),
                )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="해당 추천곡을 찾을 수 없습니다.",
                )

    finally:
        con.close()

    return {
        "record_id": record_id,
        "position": position,
        "reaction": payload.reaction,
        "saved": True,
    }


@router.get("/{record_id}/feedback")
def get_song_feedback(record_id: int = Path(gt=0)):
    """추천곡 3개의 사용자 반응을 조회합니다."""

    con = connect()

    try:
        record = con.execute(
            """
            SELECT record_id
            FROM tb_record
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()

        if record is None:
            raise HTTPException(
                status_code=404,
                detail="해당 기록을 찾을 수 없습니다.",
            )

        songs = con.execute(
            """
            SELECT song_id, recommend_order,
                   is_liked, is_skipped,
                   is_completed, is_engraved
            FROM tb_record_song
            WHERE record_id = ?
            ORDER BY recommend_order
            """,
            (record_id,),
        ).fetchall()

    finally:
        con.close()

    return {
        "record_id": record_id,
        "songs": [
            {
                "song_id": song["song_id"],
                "position": song["recommend_order"],
                "reaction": (
                    "like" if song["is_liked"]
                    else "skip" if song["is_skipped"]
                    else None
                ),
                "is_completed": bool(song["is_completed"]),
                "is_engraved": bool(song["is_engraved"]),
            }
            for song in songs
        ],
    }
