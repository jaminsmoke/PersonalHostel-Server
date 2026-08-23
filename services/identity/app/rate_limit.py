"""Cuotas de abuso con Redis (ventana fija). Fail-closed si Redis no responde."""

from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from typing import Final

import redis
from fastapi import Request, status
from redis.exceptions import RedisError

from app.client_ip import client_ip
from app.errors import RATE_LIMIT_UNAVAILABLE, RATE_LIMITED, ApiError
from app.schemas import ErrorResponse

_CLIENT: redis.Redis | None = None

DETAIL_LIMITED: Final = "Demasiadas peticiones. Inténtalo de nuevo más tarde"
DETAIL_UNAVAILABLE: Final = "El límite de peticiones no está disponible. Inténtalo de nuevo"

OPENAPI_RATE_LIMIT: Final = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorResponse,
        "description": "Demasiadas peticiones; reintenta tras Retry-After.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "El contador de cuotas no está disponible.",
    },
}


def reset_redis_client() -> None:
    """Cierra el singleton (tests)."""
    global _CLIENT
    if _CLIENT is not None:
        with contextlib.suppress(RedisError):
            _CLIENT.close()
        _CLIENT = None


def get_redis() -> redis.Redis:
    global _CLIENT
    if _CLIENT is None:
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            raise RuntimeError("REDIS_URL es obligatorio")
        _CLIENT = redis.Redis.from_url(url, decode_responses=True)
    return _CLIENT


def ping_redis() -> None:
    get_redis().ping()


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _prefix() -> str:
    return os.environ.get("RATE_LIMIT_PREFIX", "rl").strip() or "rl"


def consume(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """Incrementa el contador; 429 si supera el cupo, 503 si Redis falla."""
    redis_key = f"{_prefix()}:{bucket}:{key}"
    try:
        client = get_redis()
        count = int(client.incr(redis_key))
        if count == 1:
            client.expire(redis_key, window_seconds)
        ttl = int(client.ttl(redis_key))
        if ttl < 0:
            client.expire(redis_key, window_seconds)
            ttl = window_seconds
        if count > limit:
            raise ApiError(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code=RATE_LIMITED,
                detail=DETAIL_LIMITED,
                headers={"Retry-After": str(max(ttl, 1))},
            )
    except ApiError:
        raise
    except (RedisError, OSError, RuntimeError) as exc:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=RATE_LIMIT_UNAVAILABLE,
            detail=DETAIL_UNAVAILABLE,
        ) from exc


def enforce_refresh_ip(request: Request) -> None:
    consume(
        "refresh_ip",
        client_ip(request),
        _int_env("RATE_LIMIT_LOGIN_IP", 10),
        _int_env("RATE_LIMIT_LOGIN_IP_WINDOW", 900),
    )


def enforce_login_limits(request: Request, email: str) -> None:
    consume(
        "login_ip",
        client_ip(request),
        _int_env("RATE_LIMIT_LOGIN_IP", 10),
        _int_env("RATE_LIMIT_LOGIN_IP_WINDOW", 900),
    )
    consume(
        "login_email",
        email.strip().lower(),
        _int_env("RATE_LIMIT_LOGIN_EMAIL", 5),
        _int_env("RATE_LIMIT_LOGIN_EMAIL_WINDOW", 900),
    )


def enforce_registro_ip(request: Request) -> None:
    consume(
        "registro_ip",
        client_ip(request),
        _int_env("RATE_LIMIT_REGISTRO_IP", 5),
        _int_env("RATE_LIMIT_REGISTRO_IP_WINDOW", 3600),
    )


def enforce_upload_cuenta(account_id: uuid.UUID) -> None:
    consume(
        "upload_cuenta",
        str(account_id),
        _int_env("RATE_LIMIT_UPLOAD_CUENTA", 20),
        _int_env("RATE_LIMIT_UPLOAD_CUENTA_WINDOW", 3600),
    )


def enforce_cfc_mesa(token: str) -> None:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    consume(
        "cfc_mesa",
        digest,
        _int_env("RATE_LIMIT_CFC_MESA", 30),
        _int_env("RATE_LIMIT_CFC_MESA_WINDOW", 600),
    )
