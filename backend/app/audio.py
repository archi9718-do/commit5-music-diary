"""등록된 팀 음원 목록과 MP3 재생 응답."""

import os
from contextlib import closing
from ipaddress import ip_address
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .audio_files import resolve_audio_path
from .db import connect

router = APIRouter(prefix="/api/audio", tags=["등록 음원"])
DEFAULT_AUDIO_DIR = Path(__file__).resolve().parents[2] / "data" / "music"


def _is_local(request: Request) -> bool:
    if getattr(request.app.state, "approved_audio_only", False):
        return False
    if request.url.hostname not in {"localhost", "127.0.0.1", "::1"} or request.client is None:
        return False
    try:
        return ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _audio_root() -> Path:
    return Path(os.environ.get("MOODWAVE_AUDIO_DIR", str(DEFAULT_AUDIO_DIR))).resolve()


@router.get("")
def list_audio(request: Request):
    root = _audio_root()
    with closing(connect()) as con:
        rows = con.execute(
            """SELECT audio_id, title, artist, relative_path FROM tb_audio
               WHERE is_public_demo = 1 OR ? ORDER BY audio_id""",
            (_is_local(request),),
        ).fetchall()
    return {"tracks": [
        {"audio_id": row["audio_id"], "title": row["title"], "artist": row["artist"],
         "audio_url": f'/api/audio/{row["audio_id"]}'}
        for row in rows if resolve_audio_path(root, row["relative_path"]) is not None
    ]}


@router.get("/{audio_id}", response_class=FileResponse)
@router.head("/{audio_id}", response_class=FileResponse, include_in_schema=False)
def stream_audio(audio_id: str, request: Request):
    with closing(connect()) as con:
        row = con.execute(
            """SELECT relative_path FROM tb_audio
               WHERE audio_id = ? AND (is_public_demo = 1 OR ?)""",
            (audio_id, _is_local(request)),
        ).fetchone()
    path = resolve_audio_path(_audio_root(), row["relative_path"]) if row else None
    if path is None:
        raise HTTPException(status_code=404, detail="재생 가능한 음원을 찾을 수 없습니다.")
    # FileResponse가 브라우저 탐색에 필요한 Range 요청을 처리합니다.
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})
