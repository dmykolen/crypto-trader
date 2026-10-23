from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from trader.core.config import settings


def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def create_db_and_tables() -> None:
    from trader.models import NewsItem, Trade

    tables = [NewsItem.__table__, Trade.__table__]
    try:
        SQLModel.metadata.create_all(engine, tables=tables)
    except OperationalError as exc:
        if "already exists" not in str(exc):
            raise
        SQLModel.metadata.create_all(engine, tables=tables)
