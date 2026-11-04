import re
import secrets
import string

BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
CODE_LENGTH = 7
ALIAS_PATTERN = re.compile(r"^[a-z0-9_-]{3,30}$")
REDIRECT_CODE_PATTERN = re.compile(r"^[0-9A-Za-z_-]{3,30}$")

RESERVED_ALIASES = {
    "api",
    "admin",
    "health",
    "healthz",
    "readyz",
    "static",
    "assets",
    "favicon.ico",
    "robots.txt",
}


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(secrets.choice(BASE62) for _ in range(length))


def normalize_alias(alias: str) -> str:
    return alias.strip().lower()


def is_valid_alias(alias: str) -> bool:
    return bool(ALIAS_PATTERN.fullmatch(alias))


def is_reserved_alias(alias: str) -> bool:
    return normalize_alias(alias) in RESERVED_ALIASES
