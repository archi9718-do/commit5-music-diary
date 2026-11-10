import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import connect, init_db
from .recommender import ScoreDataError, recommend_three
from .schemas import (
    EmotionResult,
    RecommendationRequest,
    RecommendationResponse,
    RecordCreate,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
