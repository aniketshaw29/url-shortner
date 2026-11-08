import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.analytics import AnalyticsWorker
from app.api import health, links, redirect
from app.config import Settings, get_settings
from app.db import create_db_engine, create_session_factory
from app.errors import APIError
from app.metrics import HTTP_DURATION, HTTP_REQUESTS

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        worker: AnalyticsWorker | None = None
        if settings.analytics_worker_enabled:
            worker = AnalyticsWorker(
                Redis.from_url(settings.redis_url, decode_responses=True),
                session_factory,
                settings.analytics_stream,
                settings.analytics_group,
                settings.analytics_consumer,
            )
            worker.start()

        _app.state.worker = worker
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()
            redis_client.close()
            engine.dispose()

    app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_client
    app.state.worker = None

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_DURATION.labels(request.method, route_path).observe(duration_ms / 1000)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s %s %.1fms %s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        location = ".".join(
            str(part) for part in first.get("loc", ()) if part not in {"body", "query"}
        )
        message = str(first.get("msg", "Invalid request"))
        if location:
            message = f"{location}: {message}"
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": message,
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
            headers=exc.headers,
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(health.router)
    app.include_router(links.router)
    app.include_router(redirect.router)
    return app


app = create_app()
