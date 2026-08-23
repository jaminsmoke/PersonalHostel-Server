import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_camarero_db, get_negocio_db
from app.errors import (
    INVALID_TOKEN,
    NEGOCIO_INVALID_TOKEN,
    ApiError,
)
from app.internal import get_camareros_internal
from app.models import Camarero, Credencial, CredencialEstado, CuentaNegocio
from app.security import get_session_secret, get_session_secret_env
from app.sessions import (
    access_ttl,
    legacy_jwt_valido,
    maybe_touch,
    parse_iat,
    sesion_camarero_activa,
    sesion_negocio_activa,
)

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError, TypeError, ValueError:
        return False


def create_access_token(
    subject_id: uuid.UUID,
    secret: str,
    subject_type: str = "camarero",
    jti: uuid.UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject_id),
        "typ": subject_type,
        "iat": now,
        "exp": now + access_ttl(),
    }
    if jti is not None:
        payload["jti"] = str(jti)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_business_access_token(
    cuenta_id: uuid.UUID, secret: str, jti: uuid.UUID | None = None
) -> str:
    return create_access_token(cuenta_id, secret, subject_type="negocio", jti=jti)


@dataclass(frozen=True)
class AccessClaims:
    subject_id: uuid.UUID
    subject_type: str
    jti: uuid.UUID | None
    iat: datetime | None


def decode_access_claims(
    token: str, secret: str, expected_type: str | None = None
) -> AccessClaims | None:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        token_type = payload.get("typ", "camarero")
        if expected_type is not None and token_type != expected_type:
            return None
        jti_raw = payload.get("jti")
        jti = uuid.UUID(jti_raw) if jti_raw else None
        return AccessClaims(
            subject_id=uuid.UUID(payload["sub"]),
            subject_type=token_type,
            jti=jti,
            iat=parse_iat(payload.get("iat")),
        )
    except jwt.PyJWTError, KeyError, ValueError, TypeError:
        return None


def decode_access_token(
    token: str, secret: str, expected_type: str = "camarero"
) -> uuid.UUID | None:
    claims = decode_access_claims(token, secret, expected_type=expected_type)
    return None if claims is None else claims.subject_id


def get_credencial_activa(db: Session, camarero_id: uuid.UUID) -> Credencial | None:
    return (
        db.query(Credencial)
        .filter_by(camarero_id=camarero_id, estado=CredencialEstado.activa)
        .order_by(Credencial.creada_en.desc())
        .first()
    )


def _bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=INVALID_TOKEN,
            detail="Token de sesión inválido o caducado",
        )
    return credentials.credentials


def _raise_invalid(negocio: bool = False) -> None:
    if negocio:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=NEGOCIO_INVALID_TOKEN,
            detail="Token de cuenta de negocio inválido o caducado",
        )
    raise ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=INVALID_TOKEN,
        detail="Token de sesión inválido o caducado",
    )


# ── Servicio de profesionales ──────────────────────────────────────────────


def get_current_camarero(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_camarero_db),
) -> Camarero:
    token = _bearer_token(credentials)
    claims = decode_access_claims(token, get_session_secret(db), expected_type="camarero")
    if claims is None:
        _raise_invalid()
    camarero = db.get(Camarero, claims.subject_id)
    if camarero is None:
        _raise_invalid()
    if claims.jti is not None:
        sesion = sesion_camarero_activa(db, claims.jti)
        if sesion is None or sesion.camarero_id != camarero.id:
            _raise_invalid()
        sesion_id = sesion.id
        if maybe_touch(db, sesion):
            camarero = db.get(Camarero, camarero.id)
            if camarero is None:
                _raise_invalid()
        camarero._sesion_id = sesion_id  # type: ignore[attr-defined]
    else:
        if not legacy_jwt_valido(camarero.sesiones_validas_desde, claims.iat):
            _raise_invalid()
        camarero._sesion_id = None  # type: ignore[attr-defined]
    return camarero


def current_sesion_id(camarero: Camarero) -> uuid.UUID | None:
    return getattr(camarero, "_sesion_id", None)


def get_current_camarero_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_camarero_db),
) -> Camarero | None:
    """Resuelve el camarero si hay bearer válido; si no, devuelve None (magic-link)."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        return get_current_camarero(credentials, db)
    except ApiError:
        return None


# ── Servicio de negocio ────────────────────────────────────────────────────


def get_current_cuenta_negocio(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_negocio_db),
) -> CuentaNegocio:
    token = _bearer_token(credentials)
    claims = decode_access_claims(token, get_session_secret_env(), expected_type="negocio")
    if claims is None:
        _raise_invalid(negocio=True)
    cuenta = db.get(CuentaNegocio, claims.subject_id)
    if cuenta is None:
        _raise_invalid(negocio=True)
    if claims.jti is not None:
        sesion = sesion_negocio_activa(db, claims.jti)
        if sesion is None or sesion.cuenta_id != cuenta.id:
            _raise_invalid(negocio=True)
        sesion_id = sesion.id
        if maybe_touch(db, sesion):
            cuenta = db.get(CuentaNegocio, cuenta.id)
            if cuenta is None:
                _raise_invalid(negocio=True)
        cuenta._sesion_id = sesion_id  # type: ignore[attr-defined]
    else:
        if not legacy_jwt_valido(cuenta.sesiones_validas_desde, claims.iat):
            _raise_invalid(negocio=True)
        cuenta._sesion_id = None  # type: ignore[attr-defined]
    return cuenta


def current_sesion_negocio_id(cuenta: CuentaNegocio) -> uuid.UUID | None:
    return getattr(cuenta, "_sesion_id", None)


def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_negocio_db),
) -> tuple[str, uuid.UUID]:
    """Resuelve un token de profesional o de cuenta de negocio.

    Devuelve ``(tipo, subject_id)``. El camarero no se carga (vive en la otra
    BD): la sesión se valida vía el cliente interno.
    """
    token = _bearer_token(credentials)
    claims = decode_access_claims(token, get_session_secret_env())
    if claims is None:
        _raise_invalid()

    if claims.subject_type == "negocio":
        cuenta = db.get(CuentaNegocio, claims.subject_id)
        if cuenta is None:
            _raise_invalid()
        if claims.jti is not None:
            sesion = sesion_negocio_activa(db, claims.jti)
            if sesion is None or sesion.cuenta_id != cuenta.id:
                _raise_invalid()
        elif not legacy_jwt_valido(cuenta.sesiones_validas_desde, claims.iat):
            _raise_invalid()
        return "negocio", claims.subject_id

    if not get_camareros_internal().sesion_valida(claims.subject_id, claims.jti, claims.iat):
        _raise_invalid()
    return "camarero", claims.subject_id


def get_current_camarero_id_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> uuid.UUID | None:
    """Resuelve el ``camarero_id`` del bearer (servicio de negocio) o ``None``.

    El negocio no carga el ORM del camarero (vive en la otra BD); valida la
    sesión vía el cliente interno.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    claims = decode_access_claims(
        credentials.credentials, get_session_secret_env(), expected_type="camarero"
    )
    if claims is None:
        return None
    if not get_camareros_internal().sesion_valida(claims.subject_id, claims.jti, claims.iat):
        return None
    return claims.subject_id
