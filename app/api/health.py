from fastapi import APIRouter, Request
from sqlalchemy import text

from app.errors import APIError

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, str]:
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
        request.app.state.redis.ping()
    except Exception as exc:
        raise APIError(503, "not_ready", "Dependencies are unavailable") from exc
    return {"status": "ready"}
