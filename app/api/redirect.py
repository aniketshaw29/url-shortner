from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import publish_click
from app.cache import get_cached_link, set_cached_link, set_negative_cache
from app.codes import REDIRECT_CODE_PATTERN
from app.db import get_db
from app.errors import APIError
from app.models import Link
from app.rate_limit import check_rate_limit, rate_limit_headers
from app.security import get_client_ip, hash_ip
from app.timeutils import utc_now_ts

router = APIRouter(tags=["redirect"])


def _is_usable(status: str, expires_at: int | None) -> bool:
    return status == "active" and (expires_at is None or expires_at > utc_now_ts())


@router.get("/{code}")
def redirect_to_url(
    code: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    settings = request.app.state.settings
    redis_client = request.app.state.redis
    client_ip = get_client_ip(request)

    rate = check_rate_limit(
        redis_client,
        f"ratelimit:redirect:{client_ip}",
        settings.rate_limit_redirect_per_minute,
    )
    if not rate.allowed:
        headers = rate_limit_headers(rate)
        headers["Retry-After"] = str(rate.reset_seconds)
        raise APIError(429, "rate_limited", "Too many requests", headers=headers)

    if not REDIRECT_CODE_PATTERN.fullmatch(code):
        raise APIError(404, "not_found", "Short code does not exist")

    cache_hit, payload = get_cached_link(redis_client, code)
    if cache_hit:
        if payload is None:
            raise APIError(404, "not_found", "Short code does not exist")
        link_id = int(payload["link_id"])
        long_url = str(payload["long_url"])
        status = str(payload["status"])
        expires_at = payload.get("expires_at")
    else:
        link = db.scalar(select(Link).where(Link.code == code))
        if link is None:
            set_negative_cache(redis_client, code)
            raise APIError(404, "not_found", "Short code does not exist")

        link_id = link.id
        long_url = link.long_url
        status = link.status
        expires_at = link.expires_at
        set_cached_link(
            redis_client,
            code,
            {
                "link_id": link.id,
                "long_url": link.long_url,
                "status": link.status,
                "expires_at": link.expires_at,
            },
            settings.cache_ttl_seconds,
        )

    if not _is_usable(status, expires_at):
        raise APIError(410, "gone", "This link is no longer available")

    publish_click(
        redis_client,
        settings.analytics_stream,
        link_id,
        utc_now_ts(),
        hash_ip(client_ip, settings.ip_hash_salt),
        request.headers.get("user-agent"),
        _referrer(request),
    )

    headers = {"Cache-Control": "no-store", **rate_limit_headers(rate)}
    return RedirectResponse(url=long_url, status_code=302, headers=headers)


def _referrer(request: Request) -> str | None:
    return request.headers.get("referer")
