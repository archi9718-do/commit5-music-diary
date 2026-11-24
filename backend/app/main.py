import json
import logging
import sys
from contextlib import asynccontextmanager, closing
from pathlib import Path
from traceback import extract_tb

from fastapi import FastAPI, HTTPException, Request
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from . import reasons
from .audio import router as audio_router
from .db import connect, ensure_song, get_demo_user_id, init_db, save_today_record
from .post_listening import router as post_listening_router
from .reasons import router as reasons_router
from .recommender import ScoreDataError, load_recommendation_candidates, recommend_three
from .schemas import (
    MAX_RECORD_TEXT_LENGTH,
    EmotionResult,
    EngraveRequest,
    RecommendationRequest,
    RecommendationResponse,
    RecordCreate,
    SongFeedback,
    SongFeedbackUpdate,
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

try:
    # 받아쓰기(Whisper)도 같은 방식: av·torch가 없으면 서버는 켜지고 녹음 경로만 503
    from ai.stt import service as stt_service
# 의도한 넓은 예외 처리: av·torch·모델 패키지에서 어떤 오류가 나도 서버는 켜져야 합니다.
except Exception as exc:  # noqa: BLE001
    stt_service = None
    _STT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _STT_IMPORT_ERROR = ""

# 감정 분석·받아쓰기를 쓸 수 있는지 기록해 두는 상태값 (서버가 켜질 때 정해집니다)
EMOTION_STATUS = {"ready": False, "reason": "서버 시작 전"}
STT_STATUS = {"ready": False, "reason": "서버 시작 전"}


def _prepare(status: dict, service, import_error: str, label: str) -> None:
    """모델을 미리 불러옵니다. 실패해도 서버는 켜지고, 그 모델을 쓰는 경로만 503을 돌려줍니다."""
    status["ready"] = False
    if service is None:
        status["reason"] = f"{label} 패키지를 불러오지 못했습니다 ({import_error})"
        logger.warning("%s 꺼짐: %s", label, status["reason"])
        return
    try:
        service.warm_up()  # 모델을 한 번만 읽고 첫 예측을 미리 돌려 둡니다.
    # 의도한 넓은 예외 처리: 모델 폴더 없음, GPU 오류 등 어떤 오류든 서버는 켜고 해당 경로만 503
    except Exception as exc:  # noqa: BLE001
        status["reason"] = f"{label} 모델을 불러오지 못했습니다 ({type(exc).__name__}: {exc})"
        logger.warning("%s 꺼짐: %s", label, status["reason"])
        return
    status["ready"] = True
    status["reason"] = ""


def prepare_emotion_model() -> None:
    _prepare(EMOTION_STATUS, emotion_service, _EMOTION_IMPORT_ERROR, "감정 분석")


def prepare_stt_model() -> None:
    _prepare(STT_STATUS, stt_service, _STT_IMPORT_ERROR, "받아쓰기")
# -------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    prepare_emotion_model()  # 감정 모델은 서버가 켜질 때 한 번만 불러옵니다.
    prepare_stt_model()  # 받아쓰기 모델도 미리 불러와 첫 녹음이 느리지 않게 합니다.
    reasons.agent_warm_up()  # 추천 이유 에이전트도 연결을 미리 맺어 첫 요청이 10초를 넘지 않게 합니다.
    yield


app = FastAPI(
    title="MoodWave Backend (MVP)",
    description="감정 결과 -> 점수 기반 3곡 추천 -> 그날의 판 저장용 개발 서버",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(post_listening_router)
app.include_router(reasons_router)
app.include_router(audio_router)

# 로컬 React(Vite/CRA 등) 개발 서버만 허용한 설정입니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["점검"])
def health():
    return {"status": "ok", "service": "moodwave-backend"}


@app.post("/api/records", status_code=201, tags=["기록"])
def create_record(payload: RecordCreate):
    """먼저 기록 ID를 발급합니다. 이후 상현의 분석 JSON에 이 ID를 포함합니다.

    하루 1건 규칙: 같은 날 다시 부르면 새 ID 대신 오늘 기록을 덮어쓰고 같은 ID를 돌려줍니다.
    """
    con = connect()
    try:
        with con:
            record_id = save_today_record(con, get_demo_user_id(con), payload.text)
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
    # 0) 입력 검사를 모델 상태보다 먼저: 모델이 없어도 빈 글은 422로 알려 줍니다.
    #    (2,000자 초과는 RecordCreate가 이미 422로 막습니다.)
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="감정을 분석할 글이 비어 있습니다.")
    return _analyze_and_save(payload.text)


def _check_emotion_ready() -> None:
    if not EMOTION_STATUS["ready"] or emotion_service is None:
        raise HTTPException(
            status_code=503,
            detail="감정 분석을 지금 사용할 수 없습니다. POST /api/records로 기록 후 감정 버튼 4개로 진행하세요.",
        )


def _log_model_failure(label: str, exc: Exception) -> None:
    # 원문과 예외 메시지 대신 파일명·줄 번호만 기록해 실패 지점을 추적합니다.
    frames = extract_tb(exc.__traceback__)[-4:]
    locations = " <- ".join(f"{Path(frame.filename).name}:{frame.lineno}" for frame in reversed(frames))
    logger.warning("%s 실패: %s [%s]", label, type(exc).__name__, locations)


def _analyze_and_save(text: str) -> EmotionResult:
    """글 분석 → 양식 검사 → 저장. 글(analyze)과 녹음(voice) 경로가 함께 씁니다."""
    _check_emotion_ready()

    # 1) 감정 분석 먼저 (아직 DB에 아무것도 쓰지 않음)
    try:
        result = emotion_service.analyze_text(text, record_id=None)
    except Exception as exc:  # 모델 실행 중 오류
        _log_model_failure("감정 분석", exc)
        raise HTTPException(status_code=503, detail="감정 분석 중 오류가 났습니다. 잠시 후 다시 시도하세요.") from exc

    # 2) 결과 양식 검사: /api/emotions와 같은 규칙(schemas.EmotionResult)으로 확인
    try:
        checked = EmotionResult(**{**result, "record_id": 1, "text": text})  # record_id는 저장 후 채움
    except (ValidationError, TypeError) as exc:
        # 검증 예외 본문에는 사용자의 일기나 모델 입력값이 포함될 수 있습니다.
        logger.error("감정 결과 양식 오류: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="감정 결과 양식이 올바르지 않습니다.") from exc

    # 3) 기록과 감정 결과를 한 번에 저장 (/api/emotions와 같은 칸에 저장)
    con = connect()
    try:
        with con:
            record_id = save_today_record(
                con, get_demo_user_id(con), checked.text,
                emotion_pred=checked.emotion,
                confidence_level=checked.confidence,
                emotion_probs=checked.probs,
            )
    finally:
        con.close()

    return checked.model_copy(update={"record_id": record_id})


MAX_AUDIO_BYTES = 3 * 1024 * 1024  # 10초 wav(48kHz 스테레오) 약 1.9MB + 여유


@app.post("/api/records/voice", status_code=201, response_model=EmotionResult, tags=["감정 인식 연동"])
async def analyze_voice(request: Request):
    """녹음 파일을 요청 본문 그대로(raw body) 받아 받아쓰기 → 글 감정 분석 → 저장까지 합니다.

    - 응답·저장·같은 날 덮어쓰기 규칙은 POST /api/records/analyze와 같습니다.
    - 녹음은 메모리에서만 처리하고 디스크에 쓰지 않습니다(multipart 임시 파일 없음).
    - 실패하면 아무것도 저장하지 않습니다.
    """
    # 0) 크기 제한: 조금씩 읽다가 넘으면 바로 끊음 (큰 파일을 끝까지 받지 않음)
    try:
        declared_size = int(request.headers.get("content-length", "0"))
        if declared_size < 0:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="녹음 요청의 길이 정보가 올바르지 않습니다.") from exc
    if declared_size > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="녹음 파일은 3MB 이하여야 합니다.")
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="녹음 파일은 3MB 이하여야 합니다.")
        audio.extend(chunk)
    if not audio:
        raise HTTPException(status_code=400, detail="녹음 파일이 비어 있습니다.")

    # 모델 계산은 오래 걸리므로 별도 스레드에서 (서버의 다른 요청이 멈추지 않게)
    return await run_in_threadpool(_voice_to_result, bytes(audio))


def _voice_to_result(audio: bytes) -> EmotionResult:
    if not STT_STATUS["ready"] or stt_service is None:
        raise HTTPException(
            status_code=503,
            detail="받아쓰기를 지금 사용할 수 없습니다. 글로 기록해 주세요.",
        )
    _check_emotion_ready()  # 받아쓰기 전에 확인해서 헛수고를 막음

    try:
        text = stt_service.transcribe(audio)
    except ValueError as exc:  # 읽을 수 없는 녹음 파일
        raise HTTPException(status_code=400, detail="녹음 파일을 읽지 못했습니다. 다시 녹음해 주세요.") from exc
    except Exception as exc:  # 모델 실행 중 오류
        _log_model_failure("받아쓰기", exc)
        raise HTTPException(status_code=503, detail="받아쓰기 중 오류가 났습니다. 잠시 후 다시 시도하세요.") from exc

    # STT의 무음 검사에서 반환한 빈 문자열은 감정 분석·저장 전에 거절합니다.
    if not text.strip():
        raise HTTPException(status_code=422, detail="말소리를 알아듣지 못했어요. 다시 녹음하거나 글로 적어 주세요.")
    if len(text) > MAX_RECORD_TEXT_LENGTH:
        raise HTTPException(status_code=422, detail=f"받아쓴 글은 {MAX_RECORD_TEXT_LENGTH}자 이하여야 합니다.")
    return _analyze_and_save(text)


@app.post("/api/emotions", tags=["감정 인식 연동"])
def save_emotion_result(payload: EmotionResult):
    """상현의 JSON을 받아 저장하되, 예측 감정을 확정 감정으로 취급하지 않습니다."""
    con = connect()
    try:
        with con:
            cursor = con.execute(
                """UPDATE tb_record
                   SET record_text = ?, emotion_pred = ?, confidence_level = ?, emotion_probs = ?
                   WHERE record_id = ?""",
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
        candidates = load_recommendation_candidates()
        with closing(connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            recent_songs = con.execute(
                """SELECT DISTINCT rs.song_id
                   FROM tb_record AS target
                   JOIN tb_record AS prior
                     ON prior.user_id = target.user_id
                    AND prior.record_date >= date(target.record_date, '-7 days')
                    AND prior.record_date < target.record_date
                   JOIN tb_record_song AS rs ON rs.record_id = prior.record_id
                   WHERE target.record_id = ?""",
                (payload.record_id,),
            )
            songs = recommend_three(
                payload.confirmed_emotion, {row["song_id"] for row in recent_songs}, candidates=candidates,
            )
            # 새 추천 = 새 3곡 흐름 시작이므로 흐름 종료 일시도 비웁니다.
            cursor = con.execute(
                "UPDATE tb_record SET emotion_final = ?, flow_ended_at = NULL WHERE record_id = ?",
                (payload.confirmed_emotion, payload.record_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="record_id가 없습니다.")
            con.execute("DELETE FROM tb_record_song WHERE record_id = ?", (payload.record_id,))
            for song in songs:
                ensure_song(con, song.song_id, song.brightness, song.energy)
            con.executemany(
                """INSERT INTO tb_record_song
                   (record_id, recommend_order, song_id, step, valence_at_rec, arousal_at_rec)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(payload.record_id, i, song.song_id, song.step, song.brightness, song.energy)
                 for i, song in enumerate(songs, start=1)],
            )
    except ScoreDataError as exc:
        # 서버 내부의 파일 경로를 사용자에게 노출하지 않습니다.
        raise HTTPException(status_code=503, detail="음악 점수 데이터가 준비되지 않았습니다. 서버 설정을 확인하세요.") from exc
    return {"songs": songs}


@app.get("/api/records/{record_id}/lp", tags=["오늘의 판"])
def get_today_lp(record_id: int):
    """오늘의 판: 기록과 추천곡 3개, 곡별 반응을 함께 돌려줍니다.

    기존 응답 키(record_id, text, confirmed_emotion, songs[].song_id/brightness/energy/step)는 그대로이고,
    곡마다 recommend_order, title, artist, is_liked, is_skipped, is_completed, is_engraved가 추가됐습니다.
    """
    con = connect()
    try:
        # 일기/감정과 곡 목록을 같은 SQLite 스냅샷에서 읽습니다.
        con.execute("BEGIN")
        record = con.execute(
            "SELECT record_id, record_text, emotion_final, mood_after FROM tb_record WHERE record_id = ?", (record_id,)
        ).fetchone()
        if record is None:
            raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
        rows = con.execute(
            """SELECT rs.recommend_order, rs.song_id, s.title, s.artist,
                      rs.valence_at_rec AS brightness, rs.arousal_at_rec AS energy, rs.step,
                      rs.is_liked, rs.is_skipped, rs.is_completed, rs.is_engraved
               FROM tb_record_song rs JOIN tb_song s ON s.song_id = rs.song_id
               WHERE rs.record_id = ? ORDER BY rs.recommend_order""", (record_id,)
        ).fetchall()
    finally:
        con.close()
    flags = ("is_liked", "is_skipped", "is_completed", "is_engraved")
    songs = [{**dict(row), **{flag: bool(row[flag]) for flag in flags}} for row in rows]
    return {
        "record_id": record_id,
        "text": record["record_text"],
        "confirmed_emotion": record["emotion_final"],
        "mood_after": record["mood_after"],
        "songs": songs,
        "note": "LP 새김은 POST /api/records/{record_id}/engrave 로 합니다(좋아요 곡만).",
    }


def _feedback_row(con, record_id: int, recommend_order: int):
    return con.execute(
        """SELECT record_id, recommend_order, song_id, is_liked, is_skipped, is_completed, is_engraved
           FROM tb_record_song WHERE record_id = ? AND recommend_order = ?""",
        (record_id, recommend_order),
    ).fetchone()


@app.patch(
    "/api/records/{record_id}/songs/{recommend_order}",
    response_model=SongFeedback,
    tags=["추천곡 반응"],
)
def update_song_feedback(
    payload: SongFeedbackUpdate,
    record_id: int = PathParam(gt=0),
    recommend_order: int = PathParam(ge=1, le=3, description="추천 순서 1~3 (기존 position)"),
):
    """추천곡 1곡의 좋아요·건너뛰기·완청 여부를 저장합니다. 보낸 항목만 바꿉니다.

    - 좋아요를 취소하면 LP 새김도 함께 취소됩니다(LP에는 좋아요 곡만 새김).
    - 좋아요와 건너뛰기는 동시에 표시할 수 없습니다(409).
    - 건너뛴 곡을 완청으로, 완청한 곡을 건너뛰기로 동시에 표시할 수는 없습니다(409).
    """
    con = connect()
    try:
        with con:
            # 다른 PATCH가 현재 반응을 읽은 뒤 덮어쓰는 것을 막습니다.
            con.execute("BEGIN IMMEDIATE")
            row = _feedback_row(con, record_id, recommend_order)
            if row is None:
                raise HTTPException(status_code=404, detail="해당 기록의 추천곡을 찾을 수 없습니다.")
            liked = row["is_liked"] if payload.is_liked is None else int(payload.is_liked)
            skipped = row["is_skipped"] if payload.is_skipped is None else int(payload.is_skipped)
            completed = row["is_completed"] if payload.is_completed is None else int(payload.is_completed)
            if liked and skipped:
                raise HTTPException(status_code=409, detail="좋아요한 곡은 건너뛰기로 기록할 수 없습니다. 좋아요를 먼저 취소하세요.")
            if skipped and completed:
                raise HTTPException(status_code=409, detail="건너뛴 곡은 완청으로 기록할 수 없습니다.")
            engraved = row["is_engraved"] if liked else 0
            con.execute(
                """UPDATE tb_record_song
                   SET is_liked = ?, is_skipped = ?, is_completed = ?, is_engraved = ?
                   WHERE record_id = ? AND recommend_order = ?""",
                (liked, skipped, completed, engraved, record_id, recommend_order),
            )
            updated = _feedback_row(con, record_id, recommend_order)
    finally:
        con.close()
    return SongFeedback(**dict(updated))


@app.post(
    "/api/records/{record_id}/engrave",
    response_model=list[SongFeedback],
    tags=["추천곡 반응"],
)
def engrave_liked_songs(payload: EngraveRequest | None = None, record_id: int = PathParam(gt=0)):
    """선택한 좋아요 곡을 새깁니다. 본문을 생략하면 좋아요 곡을 모두 새깁니다."""
    orders = set(payload.recommend_orders) if payload is not None else {1, 2, 3}
    con = connect()
    try:
        with con:
            exists = con.execute("SELECT 1 FROM tb_record WHERE record_id = ?", (record_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
            con.execute(
                """UPDATE tb_record_song
                   SET is_engraved = is_liked AND
                       CASE recommend_order WHEN 1 THEN ? WHEN 2 THEN ? WHEN 3 THEN ? ELSE 0 END
                   WHERE record_id = ?""",
                (1 in orders, 2 in orders, 3 in orders, record_id),
            )
            rows = con.execute(
                """SELECT record_id, recommend_order, song_id, is_liked, is_skipped, is_completed, is_engraved
                   FROM tb_record_song WHERE record_id = ? ORDER BY recommend_order""",
                (record_id,),
            ).fetchall()
    finally:
        con.close()
    return [SongFeedback(**dict(row)) for row in rows]
