import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from lookout.collectors.base import RawOpening
from lookout.config import Settings, get_settings
from lookout.db import build_engine
from lookout.kb import KnowledgeBase, load_knowledge_base
from lookout.models import Opening
from lookout.openings import insert_opening
from sqlalchemy import create_engine as create_sqlalchemy_engine
from sqlalchemy import text
from sqlalchemy.engine import URL, Engine, make_url
from sqlmodel import Session


def _test_database_url() -> URL:
    configured_url = os.getenv("TEST_DATABASE_URL")
    if configured_url:
        test_url = make_url(configured_url)
    else:
        database_url = os.getenv("DATABASE_URL", get_settings().database_url)
        source_url = make_url(database_url)
        if not source_url.database:
            raise RuntimeError("DATABASE_URL must include a database name")
        test_url = source_url.set(database=f"{source_url.database}_test")

    if not test_url.database or not test_url.database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL database name must end with '_test'")

    return test_url


def _ensure_test_database(test_url: URL) -> None:
    admin_url = test_url.set(database="postgres")
    admin_engine = create_sqlalchemy_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": test_url.database},
            ).scalar_one_or_none()
            if exists is None:
                database_name = admin_engine.dialect.identifier_preparer.quote(test_url.database)
                connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    test_url = _test_database_url()
    _ensure_test_database(test_url)
    engine = build_engine(Settings(database_url=test_url.render_as_string(hide_password=False)))

    yield engine

    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    metadata = Opening.__table__.metadata
    metadata.drop_all(engine)
    metadata.create_all(engine)

    with Session(engine) as database_session:
        yield database_session

    metadata.drop_all(engine)


@pytest.fixture
def kb() -> KnowledgeBase:
    return load_knowledge_base(Path("tests/fixtures/kb"))


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def opening_fixture(session: Session) -> Opening:
    return insert_opening(
        session,
        RawOpening(
            source="fixture",
            external_id="fixture-opening-1",
            company="Globex",
            title="Senior Python Engineer",
            location="Remote",
            url="https://example.com/jobs/fixture-opening-1",
            description="We are looking for a Python developer with experience.",
            posted_at=None,
            raw={},
        ),
    )


@pytest.fixture
def client(settings: Settings, session: Session):
    from fastapi.testclient import TestClient
    from lookout.api import create_app, get_session

    app = create_app(settings)

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.state.engine.dispose()
