"""HTTP app assembly — `uv run trader serve` or `uvicorn trader.main:app`."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from trader.core.config import settings
from trader.core.db import create_db_and_tables
from trader.core.logging import configure_logging
from trader.integrations.llm import LLM
from trader.transports.http import api, system


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


def create_app() -> FastAPI:
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    system.setup_metrics(app)
    app.include_router(system.router)
    app.include_router(api.router)
    return app


app = create_app()
