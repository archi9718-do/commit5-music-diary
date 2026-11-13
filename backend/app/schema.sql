-- MoodWave DB 스키마 v5 (SQLite)
-- 기준: 테이블 명세서 v5 (2026-11-13). 서버가 켜질 때 db.init_db()가 이 파일을 실행합니다.
-- 이미 있는 표는 건드리지 않습니다(IF NOT EXISTS). 구조를 바꿨다면 개발용 DB 파일을 지우고 다시 켜세요.
-- 외래키 검사는 db.connect()에서 연결마다 켭니다(PRAGMA foreign_keys = ON).

-- ---------------------------------------------------------------------
-- 1. 회원 (tb_user)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_user (
  user_id               INTEGER PRIMARY KEY AUTOINCREMENT,              -- 회원 ID
  email                 TEXT    NOT NULL UNIQUE,                        -- 로그인 ID
  password_hash         TEXT    NOT NULL,                               -- 비밀번호 해시(원문 저장 금지)
  created_at            TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,     -- 가입 일시
  record_consent_agreed INTEGER NOT NULL DEFAULT 0
                        CHECK (record_consent_agreed IN (0, 1))         -- 녹음·기록 동의 0/1
);

-- ---------------------------------------------------------------------
-- 2. 곡 (tb_song) — 지금 CSV 점수표와 컬럼 이름을 맞춤
--    원본 음원 파일은 넣지 않음(재배포 금지). 점수·메타데이터만 저장
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_song (
  song_id        TEXT    PRIMARY KEY,                                   -- 예: deam_2, pmemo_1
  dataset        TEXT    NOT NULL CHECK (dataset IN ('DEAM', 'PMEmo')),
  original_id    TEXT    NOT NULL,                                      -- 데이터셋 원본 곡 번호
  title          TEXT,                                                  -- 곡 제목 (데이터셋 메타데이터)
  artist         TEXT,                                                  -- 아티스트 (데이터셋 메타데이터)
  valence        REAL    NOT NULL CHECK (valence BETWEEN 0 AND 1),      -- 밝기 0~1
  arousal        REAL    NOT NULL CHECK (arousal BETWEEN 0 AND 1),      -- 에너지 0~1
  valence_raw    REAL,                                                  -- 원본 척도 점수
  arousal_raw    REAL,
  raw_scale      TEXT,                                                  -- 예: 1-9
  label_type     TEXT,                                                  -- static 등
  ratings_count  INTEGER CHECK (ratings_count >= 0),                    -- 평가 인원 수
  audio_status   TEXT    NOT NULL DEFAULT 'not_checked'
                 CHECK (audio_status IN ('not_checked', 'playable', 'blocked')),
  is_public_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_public_demo IN (0, 1)), -- 공개 시연 재생 허용
  UNIQUE (dataset, original_id)
);
CREATE INDEX IF NOT EXISTS idx_song_va ON tb_song (valence, arousal);

-- ---------------------------------------------------------------------
-- 3. 꾸미기 품목 (tb_item) — 2차 개발 범위
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_item (
  item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  item_type  TEXT    NOT NULL,                                          -- SKIN / COVER 등
  price      INTEGER NOT NULL DEFAULT 0 CHECK (price >= 0),             -- 원 단위
  is_on_sale INTEGER NOT NULL DEFAULT 0 CHECK (is_on_sale IN (0, 1))
);

-- ---------------------------------------------------------------------
-- 4. 보유 꾸미기 (tb_user_item) — 2차 개발 범위
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_user_item (
  user_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES tb_user (user_id) ON DELETE CASCADE,
  item_id      INTEGER NOT NULL REFERENCES tb_item (item_id),
  acquired_by  TEXT    NOT NULL CHECK (acquired_by IN ('PURCHASE', 'ATTENDANCE')),
  is_applied   INTEGER NOT NULL DEFAULT 0 CHECK (is_applied IN (0, 1)),
  acquired_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, item_id)
);

-- ---------------------------------------------------------------------
-- 5. 하루 기록 (tb_record)
--    흐름: analyze 호출 시 행 생성(emotion_pred, confidence, probs)
--          → 사용자가 버튼으로 확인하면 emotion_final 채움 → 추천
--    같은 날 다시 기록하면 덮어쓰기: 이 행을 UPDATE하고
--          (감정·flow_ended_at은 새로, mood_after·mood_asked_at은 그대로 둠),
--          tb_record_song의 그날 추천곡 3줄은 지우고 새로 넣음
--    감상 후 질문 조건: emotion_final IN (가라앉음, 예민함) AND flow_ended_at IS NOT NULL
--          AND 서로 다른 곡 2곡 이상 is_completed = 1 AND mood_asked_at IS NULL
--    삭제는 실제 DELETE. 사진 파일은 서버가 저장소에서 따로 지워야 함
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_record (
  record_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL REFERENCES tb_user (user_id) ON DELETE CASCADE,
  record_date      TEXT    NOT NULL CHECK (date(record_date) IS NOT NULL AND record_date = date(record_date)), -- 'YYYY-MM-DD'(한국시간), 1인 1일 1건
  record_text      TEXT,                                                -- 받아쓴 글/직접 쓴 글, 사진만이면 NULL
  emotion_pred     TEXT    CHECK (emotion_pred  IN ('좋음', '무난함', '가라앉음', '예민함')),
  emotion_probs    TEXT    CHECK (emotion_probs IS NULL OR json_valid(emotion_probs)), -- 4종 확률 JSON
  confidence_level TEXT    CHECK (confidence_level IN ('높음', '중간', '낮음')),
  emotion_final    TEXT    CHECK (emotion_final IN ('좋음', '무난함', '가라앉음', '예민함')), -- 사용자 확인 감정, 이 값으로만 추천
  photo_path       TEXT,                                                -- LP 표지 사진 경로(EXIF 제거 후)
  additional_note  TEXT,                                                -- 감상 후 한 줄 메모
  flow_ended_at    TEXT,                                                -- 3곡 흐름 종료 일시(마지막 곡 끝·건너뛰기·재생 실패), 진행 중이면 NULL
  mood_after       TEXT    CHECK (mood_after IN ('조금 나아졌어요', '그대로예요', '더 무거워졌어요', '무응답')), -- 감상 후 응답
  mood_asked_at    TEXT,                                                -- 감상 후 질문을 화면에 띄운 일시, 안 띄웠으면 NULL
  created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, record_date),
  CHECK (mood_after IS NULL OR mood_asked_at IS NOT NULL)               -- 질문을 띄운 적 있어야 응답이 있을 수 있음
);
-- 참고: CHECK는 값이 NULL이면 통과하므로 "아직 안 정해짐"은 NULL로 둠

-- SQLite에는 MySQL의 ON UPDATE CURRENT_TIMESTAMP가 없어서 트리거로 대신함
CREATE TRIGGER IF NOT EXISTS trg_record_updated_at
AFTER UPDATE ON tb_record
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE tb_record SET updated_at = CURRENT_TIMESTAMP WHERE record_id = NEW.record_id;
END;

-- ---------------------------------------------------------------------
-- 6. 하루 추천곡 및 반응 (tb_record_song)
--    같은 기록으로 다시 추천하면 기존 3행을 지우고 새로 넣음(API 규칙)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_record_song (
  record_song_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id       INTEGER NOT NULL REFERENCES tb_record (record_id) ON DELETE CASCADE,
  song_id         TEXT    NOT NULL REFERENCES tb_song (song_id),
  recommend_order INTEGER NOT NULL CHECK (recommend_order BETWEEN 1 AND 3), -- 순서에 의미 있음
  step            TEXT    NOT NULL,                                     -- 맞추기 / 조금 밝게 / 더 밝게 / 에너지 낮추기 / 차분하고 조금 밝게 / 비슷한 분위기
  valence_at_rec  REAL    NOT NULL,                                     -- 추천 당시 밝기(추천 이유 근거값)
  arousal_at_rec  REAL    NOT NULL,                                     -- 추천 당시 에너지
  is_liked        INTEGER NOT NULL DEFAULT 0 CHECK (is_liked    IN (0, 1)),
  is_skipped      INTEGER NOT NULL DEFAULT 0 CHECK (is_skipped  IN (0, 1)),
  is_completed    INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1)), -- 끝까지 재생됨(재생 실패·건너뛰기는 0). 감상 후 질문 조건에 사용
  is_engraved     INTEGER NOT NULL DEFAULT 0 CHECK (is_engraved IN (0, 1)), -- LP 새김 = 좋아요 누른 곡만
  created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (record_id, recommend_order),
  UNIQUE (record_id, song_id),
  CHECK (NOT (is_skipped = 1 AND is_completed = 1)),
  CHECK (is_engraved = 0 OR is_liked = 1)                               -- 좋아요 안 한 곡은 새길 수 없음
);
CREATE INDEX IF NOT EXISTS idx_record_song_song ON tb_record_song (song_id);

-- ---------------------------------------------------------------------
-- 7. 감정별 판 기본곡 (tb_lp_base_song) — v4 신규
--    감정 4종마다 기본 추천곡 10곡. 모든 회원이 같은 목록으로 시작하고,
--    회원이 새긴 곡이 자리 1번부터 하나씩 대신함 (판을 보여 줄 때 계산)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tb_lp_base_song (
  emotion TEXT    NOT NULL CHECK (emotion IN ('좋음', '무난함', '가라앉음', '예민함')),
  slot    INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 10),               -- 판 위 자리 번호
  song_id TEXT    NOT NULL REFERENCES tb_song (song_id),
  PRIMARY KEY (emotion, slot),
  UNIQUE (emotion, song_id)                                             -- 같은 판에 같은 곡 두 번 금지
);
