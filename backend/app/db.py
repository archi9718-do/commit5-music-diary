"""SQLite 연결과 v5 스키마 준비.

표 구조는 같은 폴더의 schema.sql(테이블 명세서 v5)을 그대로 따릅니다.
이 파일에는 여러 API가 함께 쓰는 저장 규칙(하루 1건 덮어쓰기, 곡 등록)만 둡니다.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "moodwave.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# 로그인 구현 전까지 모든 기록을 이 시연용 회원 1명에게 저장합니다.
# 로그인이 붙으면 get_demo_user_id() 대신 로그인한 회원의 user_id를 넘기면 됩니다.
DEMO_USER_EMAIL = "demo@moodwave.local"
DEMO_PASSWORD_HASH = "login-not-implemented"

# 기록 날짜는 한국 날짜로 정합니다. (SQLite CURRENT_TIMESTAMP는 UTC라서 쓰지 않음)
# zoneinfo 대신 고정 +9시간을 써서 Windows에 tzdata가 없어도 동작합니다.
KST = timezone(timedelta(hours=9))

DATASET_BY_PREFIX = {"deam": "DEAM", "pmemo": "PMEmo"}


def database_path() -> Path:
    return Path(os.environ.get("MOODWAVE_DB_PATH", str(DEFAULT_DB_PATH)))


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")  # SQLite는 연결마다 켜야 외래키를 검사합니다.
    return con


def init_db() -> None:
    con = connect()
    try:
        with con:
            con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            con.execute(
                "INSERT OR IGNORE INTO tb_user (email, password_hash) VALUES (?, ?)",
                (DEMO_USER_EMAIL, DEMO_PASSWORD_HASH),
            )
    finally:
        con.close()


def get_demo_user_id(con: sqlite3.Connection) -> int:
    row = con.execute("SELECT user_id FROM tb_user WHERE email = ?", (DEMO_USER_EMAIL,)).fetchone()
    if row is None:  # init_db 전에 불린 경우를 대비
        cursor = con.execute(
            "INSERT INTO tb_user (email, password_hash) VALUES (?, ?)",
            (DEMO_USER_EMAIL, DEMO_PASSWORD_HASH),
        )
        return cursor.lastrowid
    return row["user_id"]


def today_kst() -> str:
    return datetime.now(KST).date().isoformat()


def save_today_record(
    con: sqlite3.Connection,
    user_id: int,
    text: str,
    emotion_pred: str | None = None,
    confidence_level: str | None = None,
    emotion_probs: dict[str, float] | None = None,
) -> int:
    """오늘 기록을 저장하고 record_id를 돌려줍니다. (팀 결정 2: 같은 날 다시 기록하면 덮어쓰기)

    덮어쓸 때 감정·흐름 종료·추천곡은 새로 시작하고,
    감상 후 응답(mood_after)과 질문 표시 일시(mood_asked_at)는 남겨서 질문이 하루 1번만 나오게 합니다.
    """
    probs_json = json.dumps(emotion_probs, ensure_ascii=False) if emotion_probs is not None else None
    record_date = today_kst()
    con.execute(
        """INSERT INTO tb_record
               (user_id, record_date, record_text, emotion_pred, confidence_level, emotion_probs)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (user_id, record_date) DO UPDATE SET
               record_text      = excluded.record_text,
               emotion_pred     = excluded.emotion_pred,
               confidence_level = excluded.confidence_level,
               emotion_probs    = excluded.emotion_probs,
               emotion_final    = NULL,
               flow_ended_at    = NULL""",
        (user_id, record_date, text, emotion_pred, confidence_level, probs_json),
    )
    record_id = con.execute(
        "SELECT record_id FROM tb_record WHERE user_id = ? AND record_date = ?",
        (user_id, record_date),
    ).fetchone()["record_id"]
    con.execute("DELETE FROM tb_record_song WHERE record_id = ?", (record_id,))
    return record_id


def ensure_song(con: sqlite3.Connection, song_id: str, valence: float, arousal: float) -> None:
    """추천된 곡이 tb_song에 없으면 등록합니다. (tb_record_song.song_id 외래키를 맞추기 위함)

    곡 제목·아티스트는 데이터셋 메타데이터를 넣는 단계에서 채웁니다. 여기서는 비워 둡니다.
    """
    prefix, _, original_id = song_id.partition("_")
    dataset = DATASET_BY_PREFIX.get(prefix.lower())
    if dataset is None or not original_id:
        raise ValueError(f"곡 ID 형식이 '출처_번호'가 아닙니다: {song_id}")
    con.execute(
        """INSERT INTO tb_song (song_id, dataset, original_id, valence, arousal)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (song_id) DO NOTHING""",
        (song_id, dataset, original_id, valence, arousal),
    )
