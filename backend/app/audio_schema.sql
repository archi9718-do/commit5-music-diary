-- 음원 전용 서버와 전체 서버가 공유하는 목록입니다. MP3는 서버 폴더에 저장합니다.
CREATE TABLE IF NOT EXISTS tb_audio (
  audio_id       TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  artist         TEXT NOT NULL,
  relative_path  TEXT NOT NULL UNIQUE,
  is_public_demo INTEGER NOT NULL DEFAULT 0 CHECK (is_public_demo IN (0, 1))
);
