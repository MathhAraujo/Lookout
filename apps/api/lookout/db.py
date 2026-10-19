from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from lookout.config import Settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_engine(settings: Settings) -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)


@contextmanager
def session_scope(settings: Settings) -> Iterator[Session]:
    engine = build_engine(settings)

    try:
        with Session(engine) as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise
            else:
                session.commit()
    finally:
        engine.dispose()
