"""공개 시연 승인 음원과 플레이어만 제공하는 서버."""

from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .audio import router
from .db import connect, init_audio_catalog

DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "data" / "audio-demo-dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with closing(connect()) as con, con:
        init_audio_catalog(con)
    yield


def create_app(frontend_dir: Path = DEFAULT_FRONTEND_DIR) -> FastAPI:
    index = frontend_dir / "index.html"
    assets = frontend_dir / "assets"
    if not index.is_file() or not assets.is_dir():
        raise RuntimeError(f"음원 전용 프론트를 먼저 빌드해 주세요: {frontend_dir}")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    # 터널이 루프백에서 연결되더라도 승인된 음원만 제공합니다.
    app.state.approved_audio_only = True
    app.include_router(router)

    @app.get("/")
    def audio_player():
        return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-cache"})

    icon = frontend_dir / "icon.svg"
    if icon.is_file():
        app.add_route("/icon.svg", lambda request: FileResponse(icon, media_type="image/svg+xml"), methods=["GET"])
    # 빌드 폴더 전체를 열지 않고 화면이 쓰는 자산만 제공합니다.
    app.mount("/assets", StaticFiles(directory=assets))
    return app
