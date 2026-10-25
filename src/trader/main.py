"""HTTP app assembly — `uv run trader serve` or `uvicorn trader.main:app`."""

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trader.core.config import settings
from trader.core.db import create_db_and_tables
from trader.core.logging import configure_logging
from trader.integrations.llm import LLM
from trader.transports.http import api, system, ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    app.state.llm = LLM()
    stop = asyncio.Event()
    watcher = None
    if settings.run_watcher:
        from trader.services import trading

        watcher = asyncio.create_task(trading.run_forever(stop))
    yield
    stop.set()
    if watcher is not None:
        with suppress(Exception):
            await asyncio.wait_for(watcher, 30)
    await app.state.llm.aclose()


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def _host(header: str) -> str:
    if header.startswith("["):
        return header[1:].split("]", 1)[0]
    return header.rsplit(":", 1)[0] if header.count(":") == 1 else header


async def local_only(request: Request, call_next):
    """The UI controls real-money processes, so only localhost may call it, and state changes need the UI's own header.

    The Host check stops DNS rebinding; the custom header stops other sites open in the same browser from posting to
    localhost, because a cross-origin request carrying it needs a CORS preflight this app never grants.
    """
    if _host(request.headers.get("host", "")) not in LOCAL_HOSTS:
        return JSONResponse({"detail": "this server only answers on localhost"}, status_code=403)
    if request.method in MUTATING and request.url.path.startswith("/api/") and request.headers.get("x-trader-ui") != "1":
        return JSONResponse({"detail": "state-changing requests need the X-Trader-UI: 1 header"}, status_code=403)
    return await call_next(request)


def mount_web(app: FastAPI, dist: Path = WEB_DIST) -> None:
    """Serve the built web UI (web/dist) with a single-page-app fallback; API and metrics routes keep priority."""
    if not (dist / "index.html").exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "metrics")):
            raise HTTPException(404)
        file = (dist / path).resolve()
        if path and file.is_file() and dist.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(dist / "index.html")


def create_app() -> FastAPI:
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.middleware("http")(local_only)
    system.setup_metrics(app)
    app.include_router(system.router)
    app.include_router(api.router)
    app.include_router(ui.router)
    mount_web(app)
    return app


app = create_app()
