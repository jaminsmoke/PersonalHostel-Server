import secrets
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    current_sesion_id,
    get_credencial_activa,
    get_current_camarero,
    hash_password,
    verify_password,
)
from app.data_origin import ensure_data_origin_allowed
from app.db import get_camarero_db
from app.errors import (
    CAMARERO_NOT_FOUND,
    CREDENTIAL_INACTIVE,
    CREDENTIAL_REVOKED,
    EMAIL_ALREADY_REGISTERED,
    FOTO_INEXISTENTE,
    FOTO_INVALIDA,
    PASSWORD_INCORRECTA,
    QR_INVALIDO,
    SESION_NOT_FOUND,
    ApiError,
)
from app.images import MAX_INPUT_BYTES, FotoInvalida, normalizar_foto
from app.internal import get_negocio_internal
from app.models import (
    DEFAULT_VISIBILIDAD,
    Camarero,
    Credencial,
    CredencialEstado,
    SesionCamarero,
)
from app.rate_limit import OPENAPI_RATE_LIMIT, enforce_registro_ip, enforce_upload_cuenta
from app.schemas import (
    CamareroFichaPublica,
    CamareroPerfil,
    CambioPasswordRequest,
    CambioPasswordResponse,
    ErrorResponse,
    EstablecimientoMembresiaResponse,
    FotoResponse,
    InvitacionAcceptResponse,
    InvitacionCamareroResponse,
    InvitacionRechazarResponse,
    PaginaPublicaUpdateRequest,
    PerfilUpdateRequest,
    QrResponse,
    RegistroRequest,
    RegistroResponse,
    RevocarRequest,
    RevocarResponse,
    RevocarSesionRequest,
    RevocarSesionResponse,
    SesionItem,
    SupresionRequest,
    SupresionResponse,
    VisibilidadCamarero,
    VisibilidadEstablecimientosUpdateRequest,
    VisibilidadUpdateRequest,
)
from app.security import (
    build_qr_payload,
    ficha_url,
    get_session_secret,
    get_signing_key,
    get_verify_key,
    parse_and_verify_qr_payload,
)
from app.sessions import (
    issue_camarero_session,
    revoke_all_camarero,
    revoke_sesion,
)
from app.storage import get_foto_storage

router = APIRouter(prefix="/v1/camareros", tags=["camareros"])

CLAVE_REVOCADA = "Clave revocada. Renueva la clave"

_UNAUTHORIZED = {
    "model": ErrorResponse,
    "description": "Token de sesión inválido o caducado.",
}
_CONFLICT = {
    "model": ErrorResponse,
    "description": "Cuenta sin credencial activa (revocada).",
}
_VALIDATION = {
    "model": ErrorResponse,
    "description": "Cuerpo de la petición inválido.",
}


def _visibilidad_actual(camarero: Camarero) -> dict:
    """Visibilidad completa del camarero, fusionada con los defaults."""
    vis = dict(DEFAULT_VISIBILIDAD)
    if camarero.visibilidad:
        vis.update(camarero.visibilidad)
    return vis


@router.post(
    "/registro",
    response_model=RegistroResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Ya existe un camarero con ese email.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
        **OPENAPI_RATE_LIMIT,
    },
)
def registrar_camarero(
    request: Request,
    payload: RegistroRequest,
    db: Session = Depends(get_camarero_db),
) -> RegistroResponse:
    enforce_registro_ip(request)
    ensure_data_origin_allowed(payload.data_origin)
    camarero = Camarero(
        nombre=payload.nombre.strip(),
        apellidos=payload.apellidos.strip(),
        nick=payload.nick.strip() if payload.nick else None,
        email=payload.email.lower(),
        telefono=payload.telefono.strip() if payload.telefono else None,
        direccion=payload.direccion.strip() if payload.direccion else None,
        ciudad=payload.ciudad.strip() if payload.ciudad else None,
        password_hash=hash_password(payload.password),
        data_origin=payload.data_origin,
    )
    credencial = Credencial(
        secreto=secrets.token_urlsafe(32),
        estado=CredencialEstado.activa,
    )

    signing_key = get_signing_key(db)

    try:
        db.add(camarero)
        db.flush()
        credencial.camarero_id = camarero.id
        db.add(credencial)
        db.commit()
        db.refresh(credencial)
    except IntegrityError as exc:
        db.rollback()
        if "camareros_email_key" in str(exc.orig):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code=EMAIL_ALREADY_REGISTERED,
                detail="Ya existe un camarero con ese email",
            ) from exc
        raise

    qr = build_qr_payload(camarero.id, credencial.id, signing_key)
    issued = issue_camarero_session(
        db,
        camarero.id,
        get_session_secret(db),
        payload.dispositivo,
        request.headers.get("user-agent"),
    )
    db.commit()
    return RegistroResponse(
        id=camarero.id,
        qr=qr,
        ficha_url=ficha_url(qr),
        data_origin=camarero.data_origin,
        token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        sesion_id=issued.sesion_id,
    )


@router.get(
    "/me",
    response_model=CamareroPerfil,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def me(camarero: Camarero = Depends(get_current_camarero)) -> Camarero:
    return camarero


@router.patch(
    "/me",
    response_model=CamareroPerfil,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def actualizar_me(
    payload: PerfilUpdateRequest,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> Camarero:
    if "nick" in payload.model_fields_set:
        camarero.nick = payload.nick.strip() if payload.nick else None
    if "direccion" in payload.model_fields_set:
        camarero.direccion = payload.direccion.strip() if payload.direccion else None
    if "ciudad" in payload.model_fields_set:
        camarero.ciudad = payload.ciudad.strip() if payload.ciudad else None
    db.commit()
    db.refresh(camarero)
    return camarero


@router.get(
    "/me/visibilidad",
    response_model=VisibilidadCamarero,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def obtener_visibilidad(
    camarero: Camarero = Depends(get_current_camarero),
) -> dict:
    return _visibilidad_actual(camarero)


@router.put(
    "/me/visibilidad",
    response_model=VisibilidadCamarero,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def actualizar_visibilidad(
    payload: VisibilidadUpdateRequest,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> dict:
    actual = _visibilidad_actual(camarero)
    actual.update(payload.model_dump(exclude_unset=True, exclude_none=True))
    camarero.visibilidad = actual
    db.commit()
    db.refresh(camarero)
    return _visibilidad_actual(camarero)


@router.put(
    "/me/visibilidad-establecimientos",
    response_model=CamareroPerfil,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def actualizar_visibilidad_establecimientos(
    payload: VisibilidadEstablecimientosUpdateRequest,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> Camarero:
    """Preferencia del camarero sobre aparecer en el directorio de otros
    establecimientos (siempre / solo cuando está libre / nunca).
    """
    camarero.visible_otros_establecimientos = payload.visible.value
    db.commit()
    db.refresh(camarero)
    return camarero


@router.put(
    "/me/pagina-publica",
    response_model=CamareroPerfil,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def actualizar_pagina_publica(
    payload: PaginaPublicaUpdateRequest,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> Camarero:
    """Opt-in del camarero para aparecer en la web pública de los
    establecimientos donde trabaja (matriz AND con `mostrar_equipo`).
    """
    camarero.aparecer_web_negocio = payload.aparecer_web_negocio
    db.commit()
    db.refresh(camarero)
    return camarero


def _camarero_por_qr(qr: str, db: Session) -> Camarero:
    """Devuelve el camarero si el QR es válido y su credencial está activa."""
    parsed = parse_and_verify_qr_payload(qr, get_verify_key(db))
    if parsed is None:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=QR_INVALIDO,
            detail="El QR no es válido",
        )
    camarero_id, credencial_id = parsed
    credencial = db.get(Credencial, credencial_id)
    if (
        credencial is None
        or credencial.camarero_id != camarero_id
        or credencial.estado != CredencialEstado.activa
    ):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code=CREDENTIAL_INACTIVE,
            detail="La credencial del QR no está activa",
        )
    camarero = db.get(Camarero, camarero_id)
    if camarero is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=CAMARERO_NOT_FOUND,
            detail="Camarero no encontrado",
        )
    return camarero


@router.get(
    "/ficha",
    response_model=CamareroFichaPublica,
    response_model_exclude_none=True,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
    },
)
def ficha_publica(qr: str, db: Session = Depends(get_camarero_db)) -> dict:
    """Ficha pública por QR `phid1` (sin token): solo campos visibles."""
    camarero = _camarero_por_qr(qr, db)

    ficha: dict = {
        "camarero_id": camarero.id,
        "nombre": camarero.nombre,
        "apellidos": camarero.apellidos,
    }
    if camarero.campo_visible("nick"):
        ficha["nick"] = camarero.nick
    if camarero.campo_visible("email"):
        ficha["email"] = camarero.email
    if camarero.campo_visible("telefono"):
        ficha["telefono"] = camarero.telefono
    if camarero.campo_visible("direccion"):
        ficha["direccion"] = camarero.direccion
    if camarero.campo_visible("ciudad"):
        ficha["ciudad"] = camarero.ciudad
    if camarero.campo_visible("foto") and camarero.foto_clave:
        ficha["foto_url"] = f"/v1/camareros/ficha/foto?qr={quote(qr)}"
    return ficha


@router.get(
    "/me/establecimientos",
    response_model=list[EstablecimientoMembresiaResponse],
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def mis_establecimientos(
    camarero: Camarero = Depends(get_current_camarero),
) -> list[dict]:
    return get_negocio_internal().establecimientos_de(camarero.id)


@router.get(
    "/me/invitaciones",
    response_model=list[InvitacionCamareroResponse],
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def mis_invitaciones(
    camarero: Camarero = Depends(get_current_camarero),
) -> list[dict]:
    return get_negocio_internal().invitaciones_de(camarero.id)


@router.post(
    "/me/invitaciones/{invitacion_id}/aceptar",
    response_model=InvitacionAcceptResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_410_GONE: {"model": ErrorResponse},
    },
)
def aceptar_invitacion_me(
    invitacion_id: uuid.UUID,
    camarero: Camarero = Depends(get_current_camarero),
) -> dict:
    return get_negocio_internal().aceptar_invitacion(invitacion_id, camarero.id)


@router.post(
    "/me/invitaciones/{invitacion_id}/rechazar",
    response_model=InvitacionRechazarResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_410_GONE: {"model": ErrorResponse},
    },
)
def rechazar_invitacion_me(
    invitacion_id: uuid.UUID,
    camarero: Camarero = Depends(get_current_camarero),
) -> dict:
    return get_negocio_internal().rechazar_invitacion(invitacion_id, camarero.id)


@router.get(
    "/me/qr",
    response_model=QrResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_409_CONFLICT: _CONFLICT,
    },
)
def me_qr(
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> QrResponse:
    credencial = get_credencial_activa(db, camarero.id)
    if credencial is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code=CREDENTIAL_REVOKED,
            detail=CLAVE_REVOCADA,
        )
    qr = build_qr_payload(camarero.id, credencial.id, get_signing_key(db))
    return QrResponse(qr=qr, ficha_url=ficha_url(qr))


@router.post(
    "/me/renovar",
    response_model=QrResponse,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def renovar(
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> QrResponse:
    now = datetime.now(UTC)
    activas = (
        db.query(Credencial)
        .filter_by(camarero_id=camarero.id, estado=CredencialEstado.activa)
        .all()
    )
    for cred in activas:
        cred.estado = CredencialEstado.revocada
        cred.revocada_en = now
        cred.motivo_revocacion = "renovada"

    nueva = Credencial(
        camarero_id=camarero.id,
        secreto=secrets.token_urlsafe(32),
        estado=CredencialEstado.activa,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    qr = build_qr_payload(camarero.id, nueva.id, get_signing_key(db))
    return QrResponse(qr=qr)


@router.post(
    "/me/revocar",
    response_model=RevocarResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_409_CONFLICT: _CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
    },
)
def revocar(
    payload: RevocarRequest | None = None,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> RevocarResponse:
    credencial = get_credencial_activa(db, camarero.id)
    if credencial is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code=CREDENTIAL_REVOKED,
            detail=CLAVE_REVOCADA,
        )

    motivo = "revocada"
    if payload is not None and payload.motivo:
        motivo = payload.motivo.strip() or "revocada"

    credencial.estado = CredencialEstado.revocada
    credencial.revocada_en = datetime.now(UTC)
    credencial.motivo_revocacion = motivo
    db.commit()
    return RevocarResponse(status="revocada")


_FOTO_200 = {
    "description": "Imagen de perfil (WebP).",
    "content": {"image/webp": {}},
}
_NOT_FOUND = {
    "model": ErrorResponse,
    "description": "El camarero no tiene foto de perfil.",
}


@router.post(
    "/me/foto",
    response_model=FotoResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
        **OPENAPI_RATE_LIMIT,
    },
)
async def subir_foto(
    foto: UploadFile = File(...),
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> FotoResponse:
    enforce_upload_cuenta(camarero.id)
    data = await foto.read(MAX_INPUT_BYTES + 1)
    try:
        payload, mimetype, size = normalizar_foto(data)
    except FotoInvalida as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=FOTO_INVALIDA,
            detail=str(exc),
        ) from exc

    storage = get_foto_storage()
    if camarero.foto_clave:
        storage.borrar(camarero.foto_clave)

    clave = storage.guardar(camarero.id, payload, "webp")
    camarero.foto_clave = clave
    camarero.foto_mimetype = mimetype
    camarero.foto_size = size
    camarero.foto_actualizada_en = datetime.now(UTC)
    db.commit()
    return FotoResponse(foto_url="/v1/camareros/me/foto")


@router.get(
    "/me/foto",
    responses={
        status.HTTP_200_OK: _FOTO_200,
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND,
    },
)
def obtener_foto(camarero: Camarero = Depends(get_current_camarero)) -> Response:
    if not camarero.foto_clave:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="El camarero no tiene foto de perfil",
        )
    data = get_foto_storage().leer(camarero.foto_clave)
    if data is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="La foto no está disponible",
        )
    return Response(
        content=data,
        media_type=camarero.foto_mimetype or "image/webp",
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"{camarero.foto_clave}"',
        },
    )


@router.delete(
    "/me/foto",
    response_model=FotoResponse,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def borrar_foto(
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> FotoResponse:
    if camarero.foto_clave:
        get_foto_storage().borrar(camarero.foto_clave)
    camarero.foto_clave = None
    camarero.foto_mimetype = None
    camarero.foto_size = None
    camarero.foto_actualizada_en = None
    db.commit()
    return FotoResponse(foto_url=None)


@router.get(
    "/ficha/foto",
    responses={
        status.HTTP_200_OK: _FOTO_200,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND,
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
    },
)
def ficha_foto(qr: str, db: Session = Depends(get_camarero_db)) -> Response:
    """Foto pública por QR (sin token): solo si `foto=true` y existe."""
    camarero = _camarero_por_qr(qr, db)
    if not camarero.campo_visible("foto") or not camarero.foto_clave:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="La foto no está disponible",
        )
    data = get_foto_storage().leer(camarero.foto_clave)
    if data is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="La foto no está disponible",
        )
    return Response(
        content=data,
        media_type=camarero.foto_mimetype or "image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{camarero.foto_clave}"',
        },
    )


@router.get(
    "/ficha/foto/{camarero_id}",
    responses={
        status.HTTP_200_OK: _FOTO_200,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND,
    },
)
def ficha_foto_por_id(camarero_id: uuid.UUID, db: Session = Depends(get_camarero_db)) -> Response:
    """Foto pública por id (para el directorio): solo si `foto=true` y existe."""
    camarero = db.get(Camarero, camarero_id)
    if camarero is None or not camarero.campo_visible("foto") or not camarero.foto_clave:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="La foto no está disponible",
        )
    data = get_foto_storage().leer(camarero.foto_clave)
    if data is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="La foto no está disponible",
        )
    return Response(
        content=data,
        media_type=camarero.foto_mimetype or "image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{camarero.foto_clave}"',
        },
    )


@router.delete(
    "/me",
    response_model=SupresionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
    },
)
def suprimir_cuenta(
    payload: SupresionRequest,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> SupresionResponse:
    if camarero.password_hash is None or not verify_password(
        payload.password, camarero.password_hash
    ):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=PASSWORD_INCORRECTA,
            detail="Contraseña incorrecta",
        )

    foto_clave = camarero.foto_clave
    if foto_clave:
        get_foto_storage().borrar(foto_clave)

    db.delete(camarero)
    db.commit()
    return SupresionResponse(status="borrada")


@router.post(
    "/me/password",
    response_model=CambioPasswordResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT: _VALIDATION,
    },
)
def cambiar_password(
    request: Request,
    payload: CambioPasswordRequest,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> CambioPasswordResponse:
    if camarero.password_hash is None or not verify_password(
        payload.password_actual, camarero.password_hash
    ):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=PASSWORD_INCORRECTA,
            detail="Contraseña actual incorrecta",
        )
    camarero.password_hash = hash_password(payload.password_nueva)
    revoke_all_camarero(db, camarero, "cambio_password")
    issued = issue_camarero_session(
        db,
        camarero.id,
        get_session_secret(db),
        "tras-cambio-password",
        request.headers.get("user-agent"),
    )
    db.commit()
    return CambioPasswordResponse(
        status="cambiada",
        token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        sesion_id=issued.sesion_id,
    )


@router.get(
    "/me/sesiones",
    response_model=list[SesionItem],
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def listar_sesiones(
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> list[SesionItem]:
    actual = current_sesion_id(camarero)
    filas = (
        db.query(SesionCamarero)
        .filter_by(camarero_id=camarero.id, revocada_en=None)
        .order_by(SesionCamarero.creada_en.desc())
        .all()
    )
    return [
        SesionItem(
            id=fila.id,
            etiqueta=fila.etiqueta,
            creada_en=fila.creada_en,
            ultimo_uso_en=fila.ultimo_uso_en,
            actual=actual is not None and fila.id == actual,
        )
        for fila in filas
    ]


@router.post(
    "/me/sesiones/revocar",
    response_model=RevocarSesionResponse,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def revocar_otras_sesiones(
    payload: RevocarSesionRequest | None = None,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> RevocarSesionResponse:
    motivo = (payload.motivo if payload else None) or "cerrar_otras"
    count = revoke_all_camarero(db, camarero, motivo, except_id=current_sesion_id(camarero))
    db.commit()
    return RevocarSesionResponse(status="revocada", revocadas=count)


@router.post(
    "/me/sesiones/{sesion_id}/revocar",
    response_model=RevocarSesionResponse,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
def revocar_una_sesion(
    sesion_id: uuid.UUID,
    payload: RevocarSesionRequest | None = None,
    camarero: Camarero = Depends(get_current_camarero),
    db: Session = Depends(get_camarero_db),
) -> RevocarSesionResponse:
    sesion = db.get(SesionCamarero, sesion_id)
    if sesion is None or sesion.camarero_id != camarero.id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=SESION_NOT_FOUND,
            detail="Sesión no encontrada",
        )
    if not revoke_sesion(sesion, (payload.motivo if payload else None) or "revocada"):
        return RevocarSesionResponse(status="revocada", revocadas=0)
    db.commit()
    return RevocarSesionResponse(status="revocada", revocadas=1)
