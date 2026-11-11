import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .db import connect, init_db
from .recommender import ScoreDataError, recommend_three
from .schemas import (
    EmotionResult,
    RecommendationRequest,
    RecommendationResponse,
    RecordCreate,
)

logger = logging.getLogger("moodwave")

# --- 감정 인식(상현) 연결 -------------------------------------------------
# backend/ 폴더에서 서버를 켜도 저장소 최상위의 ai/ 폴더를 찾을 수 있게 경로를 추가합니다.
REPO_ROOT = Path(__file__).resolve().parents[2]  # main.py → app → backend → 저장소 최상위
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    # torch·transformers가 없는 컴퓨터에서는 여기서 실패합니다. 실패해도 서버는 켜집니다.
    from ai.emotion import service as emotion_service
# 의도한 넓은 예외 처리: torch·모델 패키지에서 어떤 오류가 나도 서버는 켜져야 합니다.
except Exception as exc:  # noqa: BLE001
    emotion_service = None
    _EMOTION_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _EMOTION_IMPORT_ERROR = ""

# 감정 분석을 쓸 수 있는지 기록해 두는 상태값 (서버가 켜질 때 정해집니다)
EMOTION_STATUS = {"ready": False, "reason": "서버 시작 전"}


def prepare_emotion_model() -> None:
    """감정 모델을 미리 불러옵니다. 실패해도 서버는 켜지고, 분석 경로만 503을 돌려줍니다."""
    EMOTION_STATUS["ready"] = False
    if emotion_service is None:
        EMOTION_STATUS["reason"] = f"감정 분석 패키지를 불러오지 못했습니다 ({_EMOTION_IMPORT_ERROR})"
        logger.warning("감정 분석 꺼짐: %s", EMOTION_STATUS["reason"])
        return
    try:
        emotion_service.warm_up()  # 모델을 한 번만 읽고 첫 예측을 미리 돌려 둡니다.
    # 의도한 넓은 예외 처리: 모델 폴더 없음, GPU 오류 등 어떤 오류든 서버는 켜고 분석 경로만 503
    except Exception as exc:  # noqa: BLE001
        EMOTION_STATUS["reason"] = f"감정 모델을 불러오지 못했습니다 ({type(exc).__name__}: {exc})"
        logger.warning("감정 분석 꺼짐: %s", EMOTION_STATUS["reason"])
        return
    EMOTION_STATUS["ready"] = True
    EMOTION_STATUS["reason"] = ""
# -------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    prepare_emotion_model()  # 감정 모델은 서버가 켜질 때 한 번만 불러옵니다.
    yield


app = FastAPI(
    title="MoodWave Backend (MVP)",
    description="감정 결과 -> 점수 기반 3곡 추천 -> 그날의 판 저장용 개발 서버",
    version="0.1.0",
    lifespan=lifespan,
)

# 로컬 React(Vite/CRA 등) 개발 서버만 허용한 설정입니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["점검"])
def health():
    return {"status": "ok", "service": "moodwave-backend"}


@app.post("/api/records", status_code=201, tags=["기록"])
def create_record(payload: RecordCreate):
    """먼저 기록 ID를 발급합니다. 이후 상현의 분석 JSON에 이 ID를 포함합니다."""
    con = connect()
    try:
        with con:
            cursor = con.execute("INSERT INTO records (text) VALUES (?)", (payload.text,))
            record_id = cursor.lastrowid
    finally:
        con.close()
    return {"record_id": record_id, "text": payload.text}


@app.post("/api/records/analyze", status_code=201, response_model=EmotionResult, tags=["감정 인식 연동"])
def analyze_record(payload: RecordCreate):
    """글을 받아 감정을 분석하고, 성공했을 때만 기록과 감정 결과를 한 번에 저장합니다.

    - 분석에 실패하면 아무것도 저장하지 않습니다(반쪽짜리 기록 없음).
    - 응답은 POST /api/emotions의 요청과 같은 '감정 결과 양식'입니다.
    - 예측 감정은 확정 감정이 아닙니다. 추천은 사용자가 확인한 감정으로 합니다.
    """
    if not EMOTION_STATUS["ready"] or emotion_service is None:
        raise HTTPException(
            status_code=503,
            detail="감정 분석을 지금 사용할 수 없습니다. POST /api/records로 기록 후 감정 버튼 4개로 진행하세요.",
        )

    # 1) 감정 분석 먼저 (아직 DB에 아무것도 쓰지 않음)
    try:
        result = emotion_service.analyze_text(payload.text, record_id=None)
    except ValueError as exc:  # 빈 글, 너무 긴 글 등 입력 문제
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # 모델 실행 중 오류
        logger.exception("감정 분석 실패")
        raise HTTPException(status_code=503, detail="감정 분석 중 오류가 났습니다. 잠시 후 다시 시도하세요.") from exc

    # 2) 결과 양식 검사: /api/emotions와 같은 규칙(schemas.EmotionResult)으로 확인
    try:
        checked = EmotionResult(**{**result, "record_id": 1, "text": payload.text})  # record_id는 저장 후 채움
    except (ValidationError, TypeError) as exc:
        logger.error("감정 결과 양식 오류: %s", exc)
        raise HTTPException(status_code=500, detail="감정 결과 양식이 올바르지 않습니다.") from exc

    # 3) 기록과 감정 결과를 한 번에 저장 (/api/emotions와 같은 칸에 저장)
    con = connect()
    try:
        with con:
            cursor = con.execute(
                """INSERT INTO records (text, predicted_emotion, confidence, probs_json)
                   VALUES (?, ?, ?, ?)""",
                (checked.text, checked.emotion, checked.confidence,
                 json.dumps(checked.probs, ensure_ascii=False)),
            )
            record_id = cursor.lastrowid
    finally:
        con.close()

    return checked.model_copy(update={"record_id": record_id})


@app.post("/api/emotions", tags=["감정 인식 연동"])
def save_emotion_result(payload: EmotionResult):
    """상현의 JSON을 받아 저장하되, 예측 감정을 확정 감정으로 취급하지 않습니다."""
    con = connect()
    try:
        with con:
            cursor = con.execute(
                """UPDATE records
                   SET text = ?, predicted_emotion = ?, confidence = ?, probs_json = ?
                   WHERE id = ?""",
                (payload.text, payload.emotion, payload.confidence,
                 json.dumps(payload.probs, ensure_ascii=False), payload.record_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="record_id가 없습니다. 먼저 POST /api/records를 호출하세요.")
    finally:
        con.close()
    return {"record_id": payload.record_id, "predicted_emotion": payload.emotion, "saved": True}


@app.post("/api/recommendations", response_model=RecommendationResponse, tags=["3곡 추천"])
def create_recommendations(payload: RecommendationRequest):
    """확정 감정으로 3곡을 추천하고 결과를 DB에 저장합니다."""
    try:
        songs = recommend_three(payload.confirmed_emotion)
    except ScoreDataError as exc:
        # 서버 내부의 파일 경로를 사용자에게 노출하지 않습니다.
        raise HTTPException(status_code=503, detail="음악 점수 데이터가 준비되지 않았습니다. 서버 설정을 확인하세요.") from exc
    con = connect()
    try:
        with con:
            cursor = con.execute(
                "UPDATE records SET confirmed_emotion = ? WHERE id = ?",
                (payload.confirmed_emotion, payload.record_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="record_id가 없습니다.")
            con.execute("DELETE FROM recommendations WHERE record_id = ?", (payload.record_id,))
            con.executemany(
                """INSERT INTO recommendations
                   (record_id, position, song_id, brightness, energy, step)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(payload.record_id, i, song.song_id, song.brightness, song.energy, song.step)
                 for i, song in enumerate(songs, start=1)],
            )
    finally:
        con.close()
    return {"songs": songs}


@app.get("/api/records/{record_id}/lp", tags=["오늘의 판"])
def get_today_lp(record_id: int):
    """현재는 추천곡 3개를 기록한 '임시 판'입니다. 실제 새기기 규칙은 후속 개발합니다."""
    con = connect()
    try:
        record = con.execute(
            "SELECT id, text, confirmed_emotion FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        if record is None:
            raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
        songs = con.execute(
            """SELECT song_id, brightness, energy, step FROM recommendations
               WHERE record_id = ? ORDER BY position""", (record_id,)
        ).fetchall()
    finally:
        con.close()
    return {
        "record_id": record_id,
        "text": record["text"],
        "confirmed_emotion": record["confirmed_emotion"],
        "songs": [dict(song) for song in songs],
        "note": "개발용 임시 판: 좋아요·완청·감상 후 기분에 따른 실제 새기기 규칙은 미구현",
    }
