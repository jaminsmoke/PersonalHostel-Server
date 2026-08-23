"""Rutas internas servicio-a-servicio (sin auth; red de confianza).

El servicio de negocio llama a ``/internal/camareros/*`` y el de profesionales a
``/internal/camareros/{id}/establecimientos``. Solo se alcanzan en el listener
interno (``:8081``), vía ``CAMAREROS_INTERNAL_URL`` / ``NEGOCIO_INTERNAL_URL``.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.errors import CAMARERO_NOT_FOUND, EMAIL_NOT_FOUND, INVALID_TOKEN, ApiError
from app.internal import DirectCamarerosInternal, DirectNegocioInternal

camareros_internal_router = APIRouter(prefix="/internal/camareros", tags=["internal"])
negocio_internal_router = APIRouter(prefix="/internal/camareros", tags=["internal"])
sesiones_internal_router = APIRouter(prefix="/internal/sesiones", tags=["internal"])


class QrVerifyRequest(BaseModel):
    qr: str = Field(..., min_length=20, max_length=500)


class ServicioInternalRequest(BaseModel):
    establecimiento_id: uuid.UUID
    evento_id: str = Field(..., min_length=1, max_length=64)
    tipo: str = Field(default="mesa_servida", max_length=50)
    cantidad: int = Field(default=1, ge=1)
    data_origin: str = Field(default="real", max_length=20)


@camareros_internal_router.get("/buscar")
def internal_buscar(email: str) -> dict:
    perfil = DirectCamarerosInternal().buscar_por_email(email)
    if perfil is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=EMAIL_NOT_FOUND,
            detail="No hay un camarero registrado con ese email",
        )
    return perfil


@camareros_internal_router.get("/directorio")
def internal_directorio() -> list[dict]:
    """Camareros que han optado por ser visibles en el directorio (≠ nunca)."""
    return DirectCamarerosInternal().directorio()


@camareros_internal_router.get("/{camarero_id}")
def internal_perfil(camarero_id: uuid.UUID) -> dict:
    perfil = DirectCamarerosInternal().perfil(camarero_id)
    if perfil is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=CAMARERO_NOT_FOUND,
            detail="Camarero no encontrado",
        )
    return perfil


@camareros_internal_router.get("/{camarero_id}/publico")
def internal_perfil_publico(camarero_id: uuid.UUID) -> dict:
    """Campos públicos del camarero para la web del negocio (sin PII)."""
    perfil = DirectCamarerosInternal().perfil_publico(camarero_id)
    if perfil is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=CAMARERO_NOT_FOUND,
            detail="Camarero no encontrado",
        )
    return perfil


@camareros_internal_router.post("/qr/verify")
def internal_verificar_qr(payload: QrVerifyRequest) -> dict:
    camarero_id = DirectCamarerosInternal().verificar_qr(payload.qr)
    return {"camarero_id": str(camarero_id)}


@negocio_internal_router.get("/{camarero_id}/establecimientos")
def internal_establecimientos(camarero_id: uuid.UUID) -> list[dict]:
    return DirectNegocioInternal().establecimientos_de(camarero_id)


@negocio_internal_router.get("/{camarero_id}/invitaciones")
def internal_invitaciones(camarero_id: uuid.UUID) -> list[dict]:
    return DirectNegocioInternal().invitaciones_de(camarero_id)


@negocio_internal_router.post("/{camarero_id}/invitaciones/{invitacion_id}/aceptar")
def internal_aceptar_invitacion(camarero_id: uuid.UUID, invitacion_id: uuid.UUID) -> dict:
    return DirectNegocioInternal().aceptar_invitacion(invitacion_id, camarero_id)


@negocio_internal_router.post("/{camarero_id}/invitaciones/{invitacion_id}/rechazar")
def internal_rechazar_invitacion(camarero_id: uuid.UUID, invitacion_id: uuid.UUID) -> dict:
    return DirectNegocioInternal().rechazar_invitacion(invitacion_id, camarero_id)


@camareros_internal_router.post("/{camarero_id}/servicios")
def internal_registrar_servicio(camarero_id: uuid.UUID, payload: ServicioInternalRequest) -> dict:
    return DirectCamarerosInternal().registrar_servicio(
        camarero_id=camarero_id,
        establecimiento_id=payload.establecimiento_id,
        evento_id=payload.evento_id,
        tipo=payload.tipo,
        cantidad=payload.cantidad,
        data_origin=payload.data_origin,
    )


class SesionValidarRequest(BaseModel):
    camarero_id: uuid.UUID
    jti: uuid.UUID | None = None
    iat: datetime | None = None


@sesiones_internal_router.post("/validar")
def internal_validar_sesion(payload: SesionValidarRequest) -> dict:
    if not DirectCamarerosInternal().sesion_valida(payload.camarero_id, payload.jti, payload.iat):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=INVALID_TOKEN,
            detail="Token de sesión inválido o caducado",
        )
    return {"ok": True}
