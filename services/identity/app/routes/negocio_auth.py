import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    current_sesion_negocio_id,
    get_current_cuenta_negocio,
    hash_password,
    verify_password,
)
from app.data_origin import ensure_data_origin_allowed
from app.db import get_negocio_db
from app.errors import (
    CAMARERO_NOT_FOUND,
    DATA_ORIGIN_MISMATCH,
    FOTO_INEXISTENTE,
    FOTO_INVALIDA,
    NEGOCIO_EMAIL_ALREADY_REGISTERED,
    NEGOCIO_INVALID_CREDENTIALS,
    NEGOCIO_INVALID_TOKEN,
    SESION_NOT_FOUND,
    ApiError,
)
from app.images import MAX_INPUT_BYTES, FotoInvalida, normalizar_foto
from app.internal import get_camareros_internal
from app.models import CuentaNegocio, SesionNegocio
from app.rate_limit import (
    OPENAPI_RATE_LIMIT,
    enforce_login_limits,
    enforce_refresh_ip,
    enforce_registro_ip,
    enforce_upload_cuenta,
)
from app.schemas import (
    CambioPasswordRequest,
    CambioPasswordResponse,
    CuentaNegocioPerfil,
    CuentaNegocioUpdateRequest,
    ErrorResponse,
    LoginNegocioResponse,
    LoginRequest,
    LogoNegocioResponse,
    RefreshRequest,
    RefreshResponse,
    RegistroNegocioRequest,
    RegistroNegocioResponse,
    RevocarSesionRequest,
    RevocarSesionResponse,
    SesionItem,
    SupresionNegocioRequest,
    SupresionResponse,
)
from app.security import get_session_secret_env
from app.sessions import (
    hash_refresh,
    issue_negocio_session,
    revoke_all_negocio,
    revoke_sesion,
    rotate_refresh_negocio,
)
from app.storage import get_foto_storage

router = APIRouter(prefix="/v1/auth/negocio", tags=["negocio"])


@router.post(
    "/registro",
    response_model=RegistroNegocioResponse,
    status_code=status.HTTP_201_CREATED,
    responses=OPENAPI_RATE_LIMIT,
)
def registrar_negocio(
    request: Request,
    payload: RegistroNegocioRequest,
    db: Session = Depends(get_negocio_db),
) -> RegistroNegocioResponse:
    enforce_registro_ip(request)
    ensure_data_origin_allowed(payload.data_origin)
    if payload.camarero_vinculado_id is not None:
        linked_waiter = get_camareros_internal().perfil(payload.camarero_vinculado_id)
        if linked_waiter is None:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code=CAMARERO_NOT_FOUND,
                detail="Camarero no encontrado",
            )
        if linked_waiter["data_origin"] != payload.data_origin.value:
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code=DATA_ORIGIN_MISMATCH,
                detail="La cuenta y el camarero vinculado deben tener la misma procedencia",
            )
    cuenta = CuentaNegocio(
        nombre_mostrar=payload.nombre_mostrar.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        tipo_establecimiento=payload.tipo_establecimiento,
        camarero_vinculado_id=payload.camarero_vinculado_id,
        data_origin=payload.data_origin,
    )
    db.add(cuenta)
    try:
        db.commit()
        db.refresh(cuenta)
    except IntegrityError as exc:
        db.rollback()
        if "cuentas_negocio_email_key" in str(exc.orig):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code=NEGOCIO_EMAIL_ALREADY_REGISTERED,
                detail="Ya existe una cuenta de negocio con ese email",
            ) from exc
        raise
    issued = issue_negocio_session(
        db,
        cuenta.id,
        get_session_secret_env(),
        payload.dispositivo,
        request.headers.get("user-agent"),
    )
    db.commit()
    return RegistroNegocioResponse(
        id=cuenta.id,
        data_origin=cuenta.data_origin,
        token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        sesion_id=issued.sesion_id,
    )


@router.post(
    "/login",
    response_model=LoginNegocioResponse,
    responses=OPENAPI_RATE_LIMIT,
)
def login_negocio(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_negocio_db),
) -> LoginNegocioResponse:
    enforce_login_limits(request, payload.email)
    cuenta = db.query(CuentaNegocio).filter_by(email=payload.email.lower()).one_or_none()
    if cuenta is None or not verify_password(payload.password, cuenta.password_hash):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=NEGOCIO_INVALID_CREDENTIALS,
            detail="Email o contraseña de negocio incorrectos",
        )
    issued = issue_negocio_session(
        db,
        cuenta.id,
        get_session_secret_env(),
        payload.dispositivo,
        request.headers.get("user-agent"),
    )
    db.commit()
    return LoginNegocioResponse(
        token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        sesion_id=issued.sesion_id,
        cuenta=cuenta,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses=OPENAPI_RATE_LIMIT,
)
def refresh_sesion_negocio(
    request: Request,
    payload: RefreshRequest,
    db: Session = Depends(get_negocio_db),
) -> RefreshResponse:
    enforce_refresh_ip(request)
    sesion = (
        db.query(SesionNegocio)
        .filter_by(refresh_hash=hash_refresh(payload.refresh_token))
        .one_or_none()
    )
    if sesion is None:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=NEGOCIO_INVALID_TOKEN,
            detail="Token de cuenta de negocio inválido o caducado",
        )
    issued = rotate_refresh_negocio(db, sesion, get_session_secret_env())
    db.commit()
    return RefreshResponse(
        token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        sesion_id=issued.sesion_id,
    )


@router.get("/me", response_model=CuentaNegocioPerfil)
def obtener_mi_cuenta(
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
) -> CuentaNegocio:
    """Perfil canónico de la organización autenticada."""
    return cuenta


@router.patch("/me", response_model=CuentaNegocioPerfil)
def actualizar_mi_cuenta(
    payload: CuentaNegocioUpdateRequest,
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> CuentaNegocio:
    """Actualiza los datos propios de la organización, no los del local."""
    if payload.nombre_mostrar is not None:
        cuenta.nombre_mostrar = payload.nombre_mostrar.strip()
    db.commit()
    db.refresh(cuenta)
    return cuenta


@router.delete("/me", response_model=SupresionResponse)
def suprimir_negocio(
    payload: SupresionNegocioRequest,
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> SupresionResponse:
    if not verify_password(payload.password, cuenta.password_hash):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=NEGOCIO_INVALID_CREDENTIALS,
            detail="Contraseña de negocio incorrecta",
        )
    storage = get_foto_storage()
    if cuenta.logo_clave:
        storage.borrar(cuenta.logo_clave)
    for establecimiento in cuenta.establecimientos:
        if establecimiento.logo_clave:
            storage.borrar(establecimiento.logo_clave)
    db.delete(cuenta)
    db.commit()
    return SupresionResponse(status="borrada")


@router.post(
    "/me/password",
    response_model=CambioPasswordResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
def cambiar_password_negocio(
    request: Request,
    payload: CambioPasswordRequest,
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> CambioPasswordResponse:
    if not verify_password(payload.password_actual, cuenta.password_hash):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=NEGOCIO_INVALID_CREDENTIALS,
            detail="Contraseña actual de negocio incorrecta",
        )
    cuenta.password_hash = hash_password(payload.password_nueva)
    revoke_all_negocio(db, cuenta, "cambio_password")
    issued = issue_negocio_session(
        db,
        cuenta.id,
        get_session_secret_env(),
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


@router.get("/me/sesiones", response_model=list[SesionItem])
def listar_sesiones_negocio(
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> list[SesionItem]:
    actual = current_sesion_negocio_id(cuenta)
    filas = (
        db.query(SesionNegocio)
        .filter_by(cuenta_id=cuenta.id, revocada_en=None)
        .order_by(SesionNegocio.creada_en.desc())
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


@router.post("/me/sesiones/revocar", response_model=RevocarSesionResponse)
def revocar_otras_sesiones_negocio(
    payload: RevocarSesionRequest | None = None,
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> RevocarSesionResponse:
    motivo = (payload.motivo if payload else None) or "cerrar_otras"
    count = revoke_all_negocio(db, cuenta, motivo, except_id=current_sesion_negocio_id(cuenta))
    db.commit()
    return RevocarSesionResponse(status="revocada", revocadas=count)


@router.post("/me/sesiones/{sesion_id}/revocar", response_model=RevocarSesionResponse)
def revocar_una_sesion_negocio(
    sesion_id: uuid.UUID,
    payload: RevocarSesionRequest | None = None,
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> RevocarSesionResponse:
    sesion = db.get(SesionNegocio, sesion_id)
    if sesion is None or sesion.cuenta_id != cuenta.id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=SESION_NOT_FOUND,
            detail="Sesión no encontrada",
        )
    if not revoke_sesion(sesion, (payload.motivo if payload else None) or "revocada"):
        return RevocarSesionResponse(status="revocada", revocadas=0)
    db.commit()
    return RevocarSesionResponse(status="revocada", revocadas=1)


@router.post(
    "/me/logo",
    response_model=LogoNegocioResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        **OPENAPI_RATE_LIMIT,
    },
)
async def subir_logo(
    logo: UploadFile = File(...),
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> LogoNegocioResponse:
    enforce_upload_cuenta(cuenta.id)
    data = await logo.read(MAX_INPUT_BYTES + 1)
    try:
        payload, mimetype, size = normalizar_foto(data)
    except FotoInvalida as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=FOTO_INVALIDA,
            detail=str(exc),
        ) from exc

    storage = get_foto_storage()
    if cuenta.logo_clave:
        storage.borrar(cuenta.logo_clave)

    clave = storage.guardar(cuenta.id, payload, "webp")
    cuenta.logo_clave = clave
    cuenta.logo_mimetype = mimetype
    cuenta.logo_size = size
    cuenta.logo_actualizada_en = datetime.now(UTC)
    db.commit()
    return LogoNegocioResponse(logo_url="/v1/auth/negocio/me/logo")


@router.get(
    "/me/logo",
    responses={
        status.HTTP_200_OK: {"content": {"image/webp": {}}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
def obtener_logo(
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
) -> Response:
    if not cuenta.logo_clave:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="El negocio no tiene logo",
        )
    data = get_foto_storage().leer(cuenta.logo_clave)
    if data is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=FOTO_INEXISTENTE,
            detail="El logo no está disponible",
        )
    return Response(
        content=data,
        media_type=cuenta.logo_mimetype or "image/webp",
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"{cuenta.logo_clave}"',
        },
    )


@router.delete(
    "/me/logo",
    response_model=LogoNegocioResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
def borrar_logo(
    cuenta: CuentaNegocio = Depends(get_current_cuenta_negocio),
    db: Session = Depends(get_negocio_db),
) -> LogoNegocioResponse:
    if cuenta.logo_clave:
        get_foto_storage().borrar(cuenta.logo_clave)
    cuenta.logo_clave = None
    cuenta.logo_mimetype = None
    cuenta.logo_size = None
    cuenta.logo_actualizada_en = None
    db.commit()
    return LogoNegocioResponse(logo_url=None)
