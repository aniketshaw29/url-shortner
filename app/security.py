import hashlib
import hmac
import secrets

from fastapi import Request

from app.errors import APIError


def require_api_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    expected = request.app.state.settings.api_key
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise APIError(401, "unauthorized", "Missing or invalid API key")
    return token


def api_key_identity(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def hash_ip(ip_address: str, salt: str) -> bytes:
    return hmac.new(salt.encode(), ip_address.encode(), hashlib.sha256).digest()


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
