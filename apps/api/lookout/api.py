import hashlib
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from lookout.applications import (
    ApplicationLane,
    ApplicationStatus,
    application_details,
    get_application,
    list_applications,
)
from lookout.artifacts import ArtifactNotFoundError, ArtifactStoreError, build_artifact_store
from lookout.collectors.registry import build_collectors, get_collector, load_sources_config
from lookout.config import Settings, get_settings
from lookout.db import build_engine
from lookout.models import ApplicationArtifact, ConnectorHealth, Opening
from lookout.openings import get_opening
from lookout.openings import list_openings as list_openings_repo
from lookout.queue import enqueue
from lookout.routing import InvalidReviewTransition, ReviewApplicationNotFoundError
from lookout.workflow import review_application


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

    def require_application(session: Session, application_id: UUID):
        application = get_application(session, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return application

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

    @app.get("/applications")
    def applications(
        session: Annotated[Session, Depends(get_session)],
        lane: ApplicationLane | None = None,
        status: ApplicationStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict]:
        return [
            application_details(session, application)
            for application in list_applications(
                session, lane=lane, status=status, limit=limit, offset=offset
            )
        ]

    @app.get("/applications/{application_id}")
    def application_detail(
        application_id: UUID, session: Annotated[Session, Depends(get_session)]
    ) -> dict:
        return application_details(session, require_application(session, application_id))

    def review_action(session: Session, application_id: UUID, *, approve: bool) -> dict:
        try:
            application = review_application(session, application_id, approve=approve)
        except ReviewApplicationNotFoundError:
            raise HTTPException(status_code=404, detail="Application not found") from None
        except InvalidReviewTransition:
            raise HTTPException(
                status_code=409, detail="Application is not eligible for this review action"
            ) from None
        return application_details(session, application)

    @app.post("/applications/{application_id}/approve")
    def approve(application_id: UUID, session: Annotated[Session, Depends(get_session)]) -> dict:
        return review_action(session, application_id, approve=True)

    @app.post("/applications/{application_id}/decline")
    def decline(application_id: UUID, session: Annotated[Session, Depends(get_session)]) -> dict:
        return review_action(session, application_id, approve=False)

    @app.get("/applications/{application_id}/artifacts")
    def application_artifacts(
        application_id: UUID, session: Annotated[Session, Depends(get_session)]
    ) -> list[dict]:
        require_application(session, application_id)
        artifacts = session.exec(
            select(ApplicationArtifact)
            .where(
                ApplicationArtifact.application_id == application_id,
            )
            .order_by(ApplicationArtifact.created_at, ApplicationArtifact.id)
        ).all()
        return [artifact.model_dump(mode="json", exclude={"object_key"}) for artifact in artifacts]

    @app.get("/artifacts/{artifact_id}")
    def download_artifact(artifact_id: UUID, session: Annotated[Session, Depends(get_session)]):
        artifact = session.get(ApplicationArtifact, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        try:
            data = build_artifact_store(app_settings).get_bytes(artifact.object_key)
        except ArtifactNotFoundError:
            raise HTTPException(status_code=404, detail="Artifact not found") from None
        except (ArtifactStoreError, ValueError):
            raise HTTPException(status_code=503, detail="Artifact storage is unavailable") from None
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise HTTPException(status_code=502, detail="Artifact integrity check failed")
        extension = "pdf" if artifact.content_type == "application/pdf" else "json"
        return StreamingResponse(
            iter([data]),
            media_type=artifact.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.id}.{extension}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/connectors/health", response_model=list[ConnectorHealth])
    def connector_health(session: Annotated[Session, Depends(get_session)]):
        return session.exec(select(ConnectorHealth).order_by(ConnectorHealth.connector)).all()

    return app
