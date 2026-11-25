"""Thin FastAPI adapter over :class:`aipbench.core.runtime.ArthurRuntime`."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aipbench import __version__
from aipbench.core.errors import AIPBenchError, AuthenticationError
from aipbench.core.models import ParticipantEvent
from aipbench.core.runtime import ArthurRuntime
from aipbench.transport.http.observer import ArthurObserver, observer_html

LOGGER = logging.getLogger(__name__)

OBSERVER_HTML_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
OBSERVER_JSON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def _token_matches(supplied: str | None, expected: str) -> bool:
    if supplied is None:
        return False
    return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    api_version: str = "aip/1"
    session_id: str
    sequence: Any
    kind: Any
    payload: Any
    artifact_refs: Any = Field(default_factory=list)


def create_app(
    runtime: ArthurRuntime,
    *,
    session_token: str | None = None,
    observer_token: str | None = None,
) -> FastAPI:
    """Create an HTTP adapter; protocol semantics remain entirely in ``runtime``."""
    token = session_token or runtime.session_token
    app = FastAPI(
        title="Merlin-Bench Arthur",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = runtime
    observer = ArthurObserver(runtime) if observer_token is not None else None
    app.state.observer = observer

    @app.exception_handler(AIPBenchError)
    async def aipbench_error_handler(_request: Request, exc: AIPBenchError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"reason_code": exc.code, "status": "ERROR"},
        )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        prefix = "Bearer "
        if (
            authorization is None
            or not authorization.startswith(prefix)
            or not _token_matches(authorization[len(prefix) :], token)
        ):
            raise AuthenticationError()

    auth = Depends(authorize)

    if observer is not None:

        def authorize_observer(
            supplied_token: Annotated[str | None, Header(alias="X-AIP-Observer-Token")] = None,
        ) -> None:
            assert observer_token is not None
            if not _token_matches(supplied_token, observer_token):
                raise AuthenticationError()

        @app.get("/observer", include_in_schema=False)
        @app.get("/observer/", include_in_schema=False)
        def get_observer_page() -> HTMLResponse:
            return HTMLResponse(observer_html(), headers=OBSERVER_HTML_HEADERS)

        @app.get(
            "/observer/api/summary",
            dependencies=[Depends(authorize_observer)],
            include_in_schema=False,
        )
        def get_observer_summary() -> JSONResponse:
            return JSONResponse(observer.summary(), headers=OBSERVER_JSON_HEADERS)

    @app.get("/v1/session", dependencies=[auth])
    def get_session() -> dict[str, Any]:
        return runtime.get_session()

    @app.get("/v1/protocol", dependencies=[auth])
    def get_protocol() -> dict[str, Any]:
        return dict(runtime.get_protocol())

    @app.get("/v1/instance", dependencies=[auth])
    def get_instance() -> dict[str, Any]:
        return dict(runtime.get_instance())

    @app.get("/v1/status", dependencies=[auth])
    def get_status() -> dict[str, Any]:
        return runtime.get_status()

    @app.post("/v1/artifacts", dependencies=[auth])
    async def upload_artifact(request: Request) -> dict[str, Any]:
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > runtime.artifact_store.max_single_bytes:
                raise AIPBenchError(
                    "BUDGET_EXCEEDED", "artifact byte budget exceeded", http_status=413
                )
            content.extend(chunk)
        media_type = request.headers.get("content-type", "application/octet-stream")
        return dict(runtime.upload_artifact(content=bytes(content), media_type=media_type))

    @app.post("/v1/events", dependencies=[auth])
    def submit_event(request: EventRequest) -> dict[str, Any]:
        if request.api_version != "aip/1" or request.session_id != runtime.session_id:
            raise AIPBenchError("SESSION_MISMATCH", http_status=409)
        artifact_refs: Any = request.artifact_refs
        if isinstance(artifact_refs, list):
            artifact_refs = tuple(artifact_refs)
        event = ParticipantEvent(
            sequence=request.sequence,
            kind=request.kind,
            payload=request.payload,
            artifact_refs=artifact_refs,
        )
        if observer is None:
            return runtime.submit_event(event)
        response = runtime.submit_event(event)
        try:
            observer.record(
                sequence=request.sequence,
                kind=request.kind,
                payload=request.payload,
                response=response,
            )
        except Exception:
            LOGGER.exception("local observer could not record the completed interaction")
        return response

    return app


__all__ = ["EventRequest", "create_app"]
