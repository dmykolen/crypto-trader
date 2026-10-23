from fastapi import APIRouter, FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from trader.core import metrics
from trader.core.config import settings
from trader.core.db import engine

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Touches no dependency, so a slow DB never restarts the pod."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, str]:
    """Readiness: the journal database answers."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}


def setup_metrics(app: FastAPI) -> None:
    """Default per-route HTTP metrics + /metrics. Call from main.py before the routers."""
    Instrumentator(excluded_handlers=["/metrics", "/health", "/ready"]).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    metrics.open_positions.labels(mode=settings.trading_mode).set(0)
