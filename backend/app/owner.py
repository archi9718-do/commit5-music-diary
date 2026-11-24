"""참여자 코드(X-Participant)와 기록 주인 확인. main.py와 각 라우터가 함께 씁니다."""

from contextlib import closing
from typing import Annotated

from fastapi import Header, HTTPException
from fastapi import Path as PathParam

from .db import PARTICIPANT_PATTERN, connect, get_user_id, record_owner

# 형식이 틀린 코드는 FastAPI가 422로 막습니다 (헤더는 사용자가 바꿀 수 있는 입력).
Participant = Annotated[str | None, Header(alias="X-Participant", pattern=PARTICIPANT_PATTERN)]


def require_owner(con, record_id: int, participant: str | None) -> None:
    """다른 참여자의 기록이면 없는 기록처럼 404 (있는지도 알려 주지 않음)."""
    owner = record_owner(con, record_id)
    if owner is None or owner != get_user_id(con, participant):
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")


def owned_record(record_id: Annotated[int, PathParam(gt=0)], x_participant: Participant = None) -> int:
    """경로의 {record_id}를 FastAPI가 검증한 그 값 그대로 주인 확인 (잘못된 id는 422, 남의 기록은 404).

    11/24 건호 리뷰: 경로 문자열을 따로 해석하면 "+5"처럼 FastAPI는 받는 id에서 확인이 빠졌음.
    """
    with closing(connect()) as con, con:
        require_owner(con, record_id, x_participant)
    return record_id
