"""팀 음원 목록 CSV를 SQLite에 등록합니다."""

import argparse
import csv
import re
from contextlib import closing
from pathlib import Path, PurePosixPath

from .audio_files import resolve_audio_path
from .db import connect, init_audio_catalog


def import_audio(manifest: Path, audio_dir: Path) -> int:
    root = audio_dir.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("음원 폴더를 지정해 주세요.")

    rows = []
    ids = set()
    paths = set()
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"song_id", "title", "artist", "filename", "is_public_demo"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("CSV에 song_id, title, artist, filename, is_public_demo 열이 필요합니다.")
        for row in reader:
            audio_id, title, artist, filename, public = (
                (row.get(key) or "").strip()
                for key in ("song_id", "title", "artist", "filename", "is_public_demo")
            )
            if not re.fullmatch(r"custom_[0-9]+", audio_id) or not title or not artist or public not in {"0", "1"}:
                raise ValueError(f"CSV {reader.line_num}행의 곡 정보가 올바르지 않습니다.")
            relative = PurePosixPath(filename)
            if resolve_audio_path(root, filename) is None:
                raise ValueError(f"CSV {reader.line_num}행에 음원 폴더 안의 MP3 상대 경로를 입력해 주세요.")
            if audio_id in ids or relative.as_posix().casefold() in paths:
                raise ValueError(f"CSV {reader.line_num}행의 곡 ID 또는 파일 경로가 중복됩니다.")
            ids.add(audio_id)
            paths.add(relative.as_posix().casefold())
            rows.append((audio_id, title, artist, relative.as_posix(), int(public)))
    if not rows:
        raise ValueError("CSV에 등록할 곡이 없습니다.")

    # 목록 전체를 검증한 뒤에만 DB를 초기화하고 한 트랜잭션으로 등록합니다.
    with closing(connect()) as con, con:
        init_audio_catalog(con)
        con.executemany(
            """INSERT INTO tb_audio (audio_id, title, artist, relative_path, is_public_demo)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(audio_id) DO UPDATE SET
                   title = excluded.title,
                   artist = excluded.artist,
                   relative_path = excluded.relative_path,
                   is_public_demo = excluded.is_public_demo""",
            rows,
        )
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audio-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = import_audio(args.manifest, args.audio_dir)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"음원 등록 실패: {exc}\n")
    print(f"음원 {count}곡을 등록했습니다.")


if __name__ == "__main__":
    main()
