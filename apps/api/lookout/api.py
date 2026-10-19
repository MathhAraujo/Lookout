from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from lookout.collectors.registry import build_collectors, get_collector, load_sources_config
from lookout.config import Settings, get_settings
from lookout.db import build_engine
from lookout.models import Opening
from lookout.openings import get_opening
from lookout.openings import list_openings as list_openings_repo
from lookout.queue import enqueue


class CollectRequest(BaseModel):
    source: str | None = None


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI()
    app.state.settings = app_settings
    app.state.engine = build_engine(app_settings)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/openings", response_model=list[Opening])
    def get_openings(
        session: Annotated[Session, Depends(get_session)],
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Opening]:
        return list_openings_repo(session, limit=limit, offset=offset)

    @app.post("/collect", status_code=status.HTTP_202_ACCEPTED)
    def collect_openings(
        session: Annotated[Session, Depends(get_session)],
        body: Annotated[CollectRequest | None, Body()] = None,
    ) -> dict[str, int]:
        sources = load_sources_config(app_settings.sources_config)
        if body is not None and body.source:
            source_config = sources.get(body.source)
            if source_config is None:
                raise HTTPException(status_code=404, detail="Unknown collection source")
            collector = get_collector(body.source, app_settings, source_config)
            enqueue(session, "collect", {"source": collector.name})
            return {"enqueued": 1}

        collectors = build_collectors(app_settings, sources)
        for collector in collectors:
            enqueue(session, "collect", {"source": collector.name})
        return {"enqueued": len(collectors)}

    @app.post("/openings/{opening_id}/tailor", status_code=status.HTTP_202_ACCEPTED)
    def enqueue_tailor(
        opening_id: UUID,
        session: Annotated[Session, Depends(get_session)],
    ) -> dict[str, str]:
        if get_opening(session, opening_id) is None:
            raise HTTPException(status_code=404, detail="Opening not found")

        job = enqueue(session, "tailor", {"opening_id": str(opening_id)})
        return {"job_id": str(job.id)}

    return app
