from pathlib import Path, PurePosixPath


def resolve_audio_path(root: Path, filename: str) -> Path | None:
    relative = PurePosixPath(filename)
    # DB 안에도 서버별 절대 경로 대신 MP3 상대 경로만 허용합니다.
    if (relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".mp3"
            or any(char in filename for char in ("\\", ":", "\x00"))):
        return None
    try:
        path = (root / relative).resolve(strict=True)
        if path.is_relative_to(root) and path.suffix.lower() == ".mp3" and path.is_file():
            return path
    except (OSError, RuntimeError, ValueError):
        # 삭제된 파일, 접근 불가 경로, 잘못된 링크는 목록에서 제외합니다.
        return None
    return None
