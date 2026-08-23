"""Sesiones de cuenta: emisión, validación y revocación (no el QR de oficio)."""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy.orm import Session

from app.errors import INVALID_TOKEN, NEGOCIO_INVALID_TOKEN, ApiError
from app.models import Camarero, CuentaNegocio, SesionCamarero, SesionNegocio

ACCESS_HOURS_ENV = "SESSION_ACCESS_HOURS"
REFRESH_DAYS_ENV = "SESSION_REFRESH_DAYS"
TTL_DAYS_ENV = "SESSION_TTL_DAYS"
DEFAULT_ACCESS_HOURS = 12
DEFAULT_REFRESH_DAYS = 30
TOUCH_SECONDS = 300


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID


def _clip(value: str | None, size: int) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:size]


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def access_ttl() -> timedelta:
    raw_hours = os.environ.get(ACCESS_HOURS_ENV)
    if raw_hours is not None and raw_hours.strip() != "":
        return timedelta(hours=_int_env(ACCESS_HOURS_ENV, DEFAULT_ACCESS_HOURS))
    raw_days = os.environ.get(TTL_DAYS_ENV)
    if raw_days is not None and raw_days.strip() != "":
        return timedelta(days=_int_env(TTL_DAYS_ENV, 30))
    return timedelta(hours=DEFAULT_ACCESS_HOURS)


def refresh_ttl() -> timedelta:
    return timedelta(days=_int_env(REFRESH_DAYS_ENV, DEFAULT_REFRESH_DAYS))


def expires_in_seconds() -> int:
    return int(access_ttl().total_seconds())


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_iat(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    return None


def _unauthorized(negocio: bool) -> ApiError:
    if negocio:
        return ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=NEGOCIO_INVALID_TOKEN,
            detail="Token de cuenta de negocio inválido o caducado",
        )
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=INVALID_TOKEN,
        detail="Token de sesión inválido o caducado",
    )


def issue_camarero_session(
    db: Session,
    camarero_id: uuid.UUID,
    secret: str,
    etiqueta: str | None,
    user_agent: str | None,
) -> IssuedSession:
    from app.auth import create_access_token

    now = datetime.now(UTC)
    raw = secrets.token_urlsafe(32)
    sesion = SesionCamarero(
        camarero_id=camarero_id,
        refresh_hash=hash_refresh(raw),
        etiqueta=_clip(etiqueta, 80),
        user_agent=_clip(user_agent, 200),
        creada_en=now,
        ultimo_uso_en=now,
        refresh_expira_en=now + refresh_ttl(),
    )
    db.add(sesion)
    db.flush()
    token = create_access_token(camarero_id, secret, subject_type="camarero", jti=sesion.id)
    return IssuedSession(token, raw, expires_in_seconds(), sesion.id)


def issue_negocio_session(
    db: Session,
    cuenta_id: uuid.UUID,
    secret: str,
    etiqueta: str | None,
    user_agent: str | None,
) -> IssuedSession:
    from app.auth import create_access_token

    now = datetime.now(UTC)
    raw = secrets.token_urlsafe(32)
    sesion = SesionNegocio(
        cuenta_id=cuenta_id,
        refresh_hash=hash_refresh(raw),
        etiqueta=_clip(etiqueta, 80),
        user_agent=_clip(user_agent, 200),
        creada_en=now,
        ultimo_uso_en=now,
        refresh_expira_en=now + refresh_ttl(),
    )
    db.add(sesion)
    db.flush()
    token = create_access_token(cuenta_id, secret, subject_type="negocio", jti=sesion.id)
    return IssuedSession(token, raw, expires_in_seconds(), sesion.id)


def revoke_sesion(sesion: SesionCamarero | SesionNegocio, motivo: str | None) -> bool:
    if sesion.revocada_en is not None:
        return False
    sesion.revocada_en = datetime.now(UTC)
    sesion.motivo_revocacion = _clip(motivo, 200)
    return True


def revoke_all_camarero(
    db: Session, camarero: Camarero, motivo: str, except_id: uuid.UUID | None = None
) -> int:
    now = datetime.now(UTC)
    camarero.sesiones_validas_desde = now
    count = 0
    for sesion in db.query(SesionCamarero).filter_by(camarero_id=camarero.id, revocada_en=None):
        if except_id is not None and sesion.id == except_id:
            continue
        sesion.revocada_en = now
        sesion.motivo_revocacion = motivo
        count += 1
    return count


def revoke_all_negocio(
    db: Session, cuenta: CuentaNegocio, motivo: str, except_id: uuid.UUID | None = None
) -> int:
    now = datetime.now(UTC)
    cuenta.sesiones_validas_desde = now
    count = 0
    for sesion in db.query(SesionNegocio).filter_by(cuenta_id=cuenta.id, revocada_en=None):
        if except_id is not None and sesion.id == except_id:
            continue
        sesion.revocada_en = now
        sesion.motivo_revocacion = motivo
        count += 1
    return count


def sesion_camarero_activa(db: Session, jti: uuid.UUID) -> SesionCamarero | None:
    sesion = db.get(SesionCamarero, jti)
    if sesion is None or sesion.revocada_en is not None:
        return None
    return sesion


def sesion_negocio_activa(db: Session, jti: uuid.UUID) -> SesionNegocio | None:
    sesion = db.get(SesionNegocio, jti)
    if sesion is None or sesion.revocada_en is not None:
        return None
    return sesion


def legacy_jwt_valido(cutoff: datetime | None, iat: datetime | None) -> bool:
    if cutoff is None:
        return True
    if iat is None:
        return False
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return iat >= cutoff


def maybe_touch(db: Session, sesion: SesionCamarero | SesionNegocio) -> bool:
    now = datetime.now(UTC)
    ultimo = sesion.ultimo_uso_en
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=UTC)
    if (now - ultimo).total_seconds() < TOUCH_SECONDS:
        return False
    sesion.ultimo_uso_en = now
    db.commit()
    return True


def rotate_refresh_camarero(db: Session, sesion: SesionCamarero, secret: str) -> IssuedSession:
    from app.auth import create_access_token

    now = datetime.now(UTC)
    expira = sesion.refresh_expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=UTC)
    if sesion.revocada_en is not None or expira < now:
        raise _unauthorized(False)
    raw = secrets.token_urlsafe(32)
    sesion.refresh_hash = hash_refresh(raw)
    sesion.refresh_expira_en = now + refresh_ttl()
    sesion.ultimo_uso_en = now
    db.flush()
    token = create_access_token(sesion.camarero_id, secret, subject_type="camarero", jti=sesion.id)
    return IssuedSession(token, raw, expires_in_seconds(), sesion.id)


def rotate_refresh_negocio(db: Session, sesion: SesionNegocio, secret: str) -> IssuedSession:
    from app.auth import create_access_token

    now = datetime.now(UTC)
    expira = sesion.refresh_expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=UTC)
    if sesion.revocada_en is not None or expira < now:
        raise _unauthorized(True)
    raw = secrets.token_urlsafe(32)
    sesion.refresh_hash = hash_refresh(raw)
    sesion.refresh_expira_en = now + refresh_ttl()
    sesion.ultimo_uso_en = now
    db.flush()
    token = create_access_token(sesion.cuenta_id, secret, subject_type="negocio", jti=sesion.id)
    return IssuedSession(token, raw, expires_in_seconds(), sesion.id)
