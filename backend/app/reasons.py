"""추천 이유 경로: 오늘의 사실을 DB에서 모아 에이전트(ai/agent)에 넘기고, 실패하면 템플릿 문장을 돌려줍니다.

결과는 DB에 저장하지 않습니다. 화면이 받은 문장을 그날 기록에 함께 저장합니다.
"""

import logging
import sys
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam

from .db import connect
from .schemas import ReasonsResponse

REPO_ROOT = Path(__file__).resolve().parents[2]  # main.py와 같은 이유: 저장소 최상위의 ai/를 찾기 위함
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent.rules import is_risk, template_reasons  # 규칙은 표준 라이브러리만 씀

try:
    from ai.agent.service import ready as agent_ready
    from ai.agent.service import write_reasons
# 의도한 넓은 예외 처리: 에이전트를 못 불러와도 서버는 켜지고 이 경로는 템플릿 문장을 씁니다.
except Exception:  # noqa: BLE001
    def agent_ready() -> bool:
        return False

    write_reasons = None

logger = logging.getLogger("moodwave")
router = APIRouter(prefix="/api/records", tags=["추천 이유"])


@router.post("/{record_id}/reasons", response_model=ReasonsResponse)
def create_reasons(record_id: int = PathParam(gt=0)):
    """곡마다 이유 한 줄. 위험 표현 기록은 LLM을 부르지 않고 risk=true. 실패해도 200 + 템플릿."""
    with closing(connect()) as con:
        record = con.execute(
            "SELECT user_id, record_date, record_text, emotion_final FROM tb_record WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if record is None:
            raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
        songs = con.execute(
            """SELECT recommend_order, song_id, step, valence_at_rec AS brightness, arousal_at_rec AS energy
               FROM tb_record_song WHERE record_id = ? ORDER BY recommend_order""",
            (record_id,),
        ).fetchall()
        if len(songs) != 3 or record["emotion_final"] is None:
            raise HTTPException(status_code=409, detail="추천을 먼저 받아야 이유를 만들 수 있습니다.")
        recent = con.execute(
            """SELECT record_date, emotion_final FROM tb_record
               WHERE user_id = ? AND record_date >= date(?, '-7 days') AND record_date < ?
                 AND emotion_final IS NOT NULL
               ORDER BY record_date""",
            (record["user_id"], record["record_date"], record["record_date"]),
        ).fetchall()
    # DB 연결을 닫은 뒤 에이전트를 부릅니다 (최대 10초 동안 잠금을 잡지 않게).

    emotion = record["emotion_final"]
    songs = [dict(row) for row in songs]
    texts = template_reasons(emotion, [song["step"] for song in songs])
    source, risk = "template", is_risk(record["record_text"])
    if not risk and agent_ready():
        facts = {
            "today": {"confirmed_emotion": emotion, "taste_side": None},  # taste_side: 취향 유형 작업 4 뒤에 채움
            "songs": songs,
            "recent_moods": [{"date": row["record_date"], "emotion": row["emotion_final"]} for row in recent],
        }
        try:
            result = write_reasons(facts)
        except Exception as exc:  # noqa: BLE001 - 두 번째 겹: 에이전트가 예외를 던져도 템플릿
            logger.warning("추천 이유 실패: %s", type(exc).__name__)
            result = {"texts": None}
        if result.get("texts"):
            texts, source = result["texts"], "agent"

    return {
        "source": source,
        "risk": risk,
        "reasons": [
            {"recommend_order": song["recommend_order"], "song_id": song["song_id"], "text": text}
            for song, text in zip(songs, texts, strict=True)
        ],
    }
