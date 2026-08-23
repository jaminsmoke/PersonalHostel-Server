"""Cliente interno entre los dos servicios (profesionales ↔ negocio).

Es la única vía para cruzar la frontera entre las dos bases de datos
(``identity_camareros`` y ``identity_negocio``): cada servicio tiene su propia
BD y no puede leer la del otro. Para las pocas consultas que cruzan la frontera
(buscar/verificar camarero, listar establecimientos de un camarero) se usa este
cliente, con dos transportes:

- ``direct`` (default, tests y ejecución en un solo proceso): consulta la BD del
  otro servicio directamente, sin red.
- ``http`` (Docker Compose / VPS): llama a las rutas ``/internal/*`` del otro
  servicio en el listener interno (``:8081``) mediante httpx.

El transporte se elige con la variable ``INTERNAL_TRANSPORT`` (``direct`` por
defecto). En ``http`` se requieren ``CAMAREROS_INTERNAL_URL`` y
``NEGOCIO_INTERNAL_URL``.
"""

import os
import uuid
from datetime import datetime
from typing import Protocol

import httpx2 as httpx
from fastapi import status

from app.db import CamareroSessionLocal, NegocioSessionLocal
from app.errors import (
    CAMARERO_NOT_FOUND,
    CREDENTIAL_INACTIVE,
    QR_INVALIDO,
    ApiError,
)
from app.models import (
    Camarero,
    Credencial,
    CredencialEstado,
    DataOrigin,
    Establecimiento,
    Membresia,
    MembresiaEstado,
    Servicio,
)
from app.security import get_verify_key, parse_and_verify_qr_payload

TRANSPORT_ENV = "INTERNAL_TRANSPORT"
CAMAREROS_URL_ENV = "CAMAREROS_INTERNAL_URL"
NEGOCIO_URL_ENV = "NEGOCIO_INTERNAL_URL"

TIMEOUT = 5.0


def _perfil_dict(c: Camarero) -> dict:
    return {
        "id": str(c.id),
        "nombre": c.nombre,
        "apellidos": c.apellidos,
        "email": c.email,
        "nick": c.nick,
        "data_origin": c.data_origin.value,
        "visible_otros_establecimientos": c.visible_otros_establecimientos,
        "aparecer_web_negocio": c.aparecer_web_negocio,
    }


def _perfil_publico_dict(c: Camarero) -> dict:
    """Campos públicos del camarero para la web del negocio (sin email ni PII).

    La ficha ajena en la página pública respeta la visibilidad por campo del
    camarero y su opt-in ``aparecer_web_negocio`` (matriz AND con el local).
    """
    return {
        "camarero_id": str(c.id),
        "nombre": c.nombre,
        "apellidos": c.apellidos,
        "nick": c.nick if c.campo_visible("nick") else None,
        "foto_publica": bool(c.campo_visible("foto") and c.foto_clave),
        "aparecer_web_negocio": c.aparecer_web_negocio,
    }


def _directorio_dict(c: Camarero) -> dict:
    """Entrada del directorio de camareros que han optado por ser visibles.

    Sin email (privacidad). ``foto_publica`` indica si la foto es pública
    (opt-in) y existe, para que el servicio de negocio construya la URL.
    """
    return {
        "id": str(c.id),
        "nombre": c.nombre,
        "apellidos": c.apellidos,
        "nick": c.nick,
        "foto_publica": bool(c.campo_visible("foto") and c.foto_clave),
        "visible_otros_establecimientos": c.visible_otros_establecimientos,
        "data_origin": c.data_origin.value,
    }


def _servicio_dict(s: Servicio, duplicado: bool) -> dict:
    return {
        "id": str(s.id),
        "camarero_id": str(s.camarero_id),
        "establecimiento_id": str(s.establecimiento_id),
        "evento_id": s.evento_id,
        "tipo": s.tipo,
        "cantidad": s.cantidad,
        "duplicado": duplicado,
    }


class CamarerosInternal(Protocol):
    def buscar_por_email(self, email: str) -> dict | None:
        """Perfil del camarero por email, o ``None`` si no existe."""

    def perfil(self, camarero_id: uuid.UUID) -> dict | None:
        """Perfil del camarero por id, o ``None`` si no existe."""

    def perfil_publico(self, camarero_id: uuid.UUID) -> dict | None:
        """Campos públicos del camarero para la web del negocio, o ``None``.

        Sin email ni datos privados; respeta la visibilidad por campo y el
        opt-in ``aparecer_web_negocio`` del camarero.
        """

    def verificar_qr(self, qr: str) -> uuid.UUID:
        """Devuelve ``camarero_id`` si el QR es válido y su credencial activa.

        Lanza 422 ``qr_invalido`` o 409 ``credencial_inactiva``.
        """

    def directorio(self) -> list[dict]:
        """Camareros que han optado por ser visibles en el directorio (≠ nunca).

        Sin email; el servicio de negocio aplica los filtros de "libre", dueños,
        miembros propios y ``data_origin``.
        """

    def sesion_valida(
        self,
        camarero_id: uuid.UUID,
        jti: uuid.UUID | None,
        iat: datetime | None,
    ) -> bool:
        """True si el JWT de camarero sigue siendo una sesión válida."""

    def registrar_servicio(
        self,
        camarero_id: uuid.UUID,
        establecimiento_id: uuid.UUID,
        evento_id: str,
        tipo: str,
        cantidad: int,
        data_origin: str,
    ) -> dict:
        """Registra un evento de servicio (idempotente por ``evento_id``)."""


class NegocioInternal(Protocol):
    def establecimientos_de(self, camarero_id: uuid.UUID) -> list[dict]:
        """Establecimientos activos del camarero con su rol."""

    def invitaciones_de(self, camarero_id: uuid.UUID) -> list[dict]:
        """Invitaciones dirigidas al email del camarero."""

    def aceptar_invitacion(self, invitacion_id: uuid.UUID, camarero_id: uuid.UUID) -> dict:
        """Acepta una invitación por id; devuelve la membresía resultante."""

    def rechazar_invitacion(self, invitacion_id: uuid.UUID, camarero_id: uuid.UUID) -> dict:
        """Rechaza una invitación por id; devuelve el estado resultante."""


class DirectCamarerosInternal:
    def buscar_por_email(self, email: str) -> dict | None:
        with CamareroSessionLocal() as db:
            c = db.query(Camarero).filter_by(email=email.lower()).one_or_none()
        return _perfil_dict(c) if c else None

    def perfil(self, camarero_id: uuid.UUID) -> dict | None:
        with CamareroSessionLocal() as db:
            c = db.get(Camarero, camarero_id)
        return _perfil_dict(c) if c else None

    def perfil_publico(self, camarero_id: uuid.UUID) -> dict | None:
        with CamareroSessionLocal() as db:
            c = db.get(Camarero, camarero_id)
        return _perfil_publico_dict(c) if c else None

    def verificar_qr(self, qr: str) -> uuid.UUID:
        with CamareroSessionLocal() as db:
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
            return camarero_id

    def directorio(self) -> list[dict]:
        with CamareroSessionLocal() as db:
            rows = (
                db.query(Camarero)
                .filter(Camarero.visible_otros_establecimientos != "nunca")
                .order_by(Camarero.nombre, Camarero.apellidos)
                .all()
            )
        return [_directorio_dict(c) for c in rows]

    def sesion_valida(
        self,
        camarero_id: uuid.UUID,
        jti: uuid.UUID | None,
        iat: datetime | None,
    ) -> bool:
        from app.sessions import legacy_jwt_valido, sesion_camarero_activa

        with CamareroSessionLocal() as db:
            camarero = db.get(Camarero, camarero_id)
            if camarero is None:
                return False
            if jti is not None:
                sesion = sesion_camarero_activa(db, jti)
                return sesion is not None and sesion.camarero_id == camarero_id
            return legacy_jwt_valido(camarero.sesiones_validas_desde, iat)

    def registrar_servicio(
        self,
        camarero_id: uuid.UUID,
        establecimiento_id: uuid.UUID,
        evento_id: str,
        tipo: str,
        cantidad: int,
        data_origin: str,
    ) -> dict:
        with CamareroSessionLocal() as db:
            existente = (
                db.query(Servicio)
                .filter_by(establecimiento_id=establecimiento_id, evento_id=evento_id)
                .one_or_none()
            )
            if existente is not None:
                return _servicio_dict(existente, duplicado=True)
            servicio = Servicio(
                camarero_id=camarero_id,
                establecimiento_id=establecimiento_id,
                evento_id=evento_id,
                tipo=tipo,
                cantidad=cantidad,
                data_origin=DataOrigin(data_origin),
            )
            db.add(servicio)
            db.commit()
            db.refresh(servicio)
            return _servicio_dict(servicio, duplicado=False)


class DirectNegocioInternal:
    def establecimientos_de(self, camarero_id: uuid.UUID) -> list[dict]:
        with NegocioSessionLocal() as db:
            rows = (
                db.query(Establecimiento, Membresia.rol)
                .join(Membresia, Membresia.establecimiento_id == Establecimiento.id)
                .filter(
                    Membresia.camarero_id == camarero_id,
                    Membresia.estado == MembresiaEstado.activa,
                )
                .all()
            )
        return [
            {
                "id": str(e.id),
                "nombre": e.nombre,
                "cuenta_negocio_id": str(e.cuenta_negocio_id),
                "data_origin": e.data_origin.value,
                "visible_directorio": e.visible_directorio,
                "rol": rol.value,
            }
            for e, rol in rows
        ]

    def invitaciones_de(self, camarero_id: uuid.UUID) -> list[dict]:
        from app.membresias import listar_invitaciones

        return listar_invitaciones(camarero_id)

    def aceptar_invitacion(self, invitacion_id: uuid.UUID, camarero_id: uuid.UUID) -> dict:
        from app.membresias import aceptar_invitacion_por_id

        return aceptar_invitacion_por_id(camarero_id, invitacion_id)

    def rechazar_invitacion(self, invitacion_id: uuid.UUID, camarero_id: uuid.UUID) -> dict:
        from app.membresias import rechazar_invitacion_por_id

        return rechazar_invitacion_por_id(camarero_id, invitacion_id)


def _raise_from_response(response: httpx.Response, fallback_code: str) -> None:
    try:
        body = response.json()
    except ValueError:
        body = {}
    raise ApiError(
        status_code=response.status_code,
        code=body.get("code", fallback_code),
        detail=body.get("detail", "Error interno entre servicios"),
    )


class HttpCamarerosInternal:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return httpx.request(method, f"{self.base_url}{path}", timeout=TIMEOUT, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="identity.internal_unavailable",
                detail="Servicio de profesionales no disponible",
            ) from exc

    def buscar_por_email(self, email: str) -> dict | None:
        response = self._request("GET", "/internal/camareros/buscar", params={"email": email})
        if response.status_code == status.HTTP_404_NOT_FOUND:
            return None
        if response.status_code != 200:
            _raise_from_response(response, CAMARERO_NOT_FOUND)
        return response.json()

    def perfil(self, camarero_id: uuid.UUID) -> dict | None:
        response = self._request("GET", f"/internal/camareros/{camarero_id}")
        if response.status_code == status.HTTP_404_NOT_FOUND:
            return None
        if response.status_code != 200:
            _raise_from_response(response, CAMARERO_NOT_FOUND)
        return response.json()

    def perfil_publico(self, camarero_id: uuid.UUID) -> dict | None:
        response = self._request("GET", f"/internal/camareros/{camarero_id}/publico")
        if response.status_code == status.HTTP_404_NOT_FOUND:
            return None
        if response.status_code != 200:
            _raise_from_response(response, CAMARERO_NOT_FOUND)
        return response.json()

    def verificar_qr(self, qr: str) -> uuid.UUID:
        response = self._request("POST", "/internal/camareros/qr/verify", json={"qr": qr})
        if response.status_code != 200:
            _raise_from_response(response, QR_INVALIDO)
        return uuid.UUID(response.json()["camarero_id"])

    def directorio(self) -> list[dict]:
        response = self._request("GET", "/internal/camareros/directorio")
        if response.status_code != 200:
            _raise_from_response(response, "identity.internal_error")
        return response.json()

    def sesion_valida(
        self,
        camarero_id: uuid.UUID,
        jti: uuid.UUID | None,
        iat: datetime | None,
    ) -> bool:
        body: dict = {"camarero_id": str(camarero_id)}
        if jti is not None:
            body["jti"] = str(jti)
        if iat is not None:
            body["iat"] = iat.isoformat()
        response = self._request("POST", "/internal/sesiones/validar", json=body)
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            return False
        if response.status_code == status.HTTP_404_NOT_FOUND:
            return False
        if response.status_code != 200:
            _raise_from_response(response, CAMARERO_NOT_FOUND)
        return True

    def registrar_servicio(
        self,
        camarero_id: uuid.UUID,
        establecimiento_id: uuid.UUID,
        evento_id: str,
        tipo: str,
        cantidad: int,
        data_origin: str,
    ) -> dict:
        response = self._request(
            "POST",
            f"/internal/camareros/{camarero_id}/servicios",
            json={
                "establecimiento_id": str(establecimiento_id),
                "evento_id": evento_id,
                "tipo": tipo,
                "cantidad": cantidad,
                "data_origin": data_origin,
            },
        )
        if response.status_code != 200:
            _raise_from_response(response, "identity.internal_error")
        return response.json()


class HttpNegocioInternal:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str) -> httpx.Response:
        try:
            return httpx.request(method, f"{self.base_url}{path}", timeout=TIMEOUT)
        except httpx.HTTPError as exc:
            raise ApiError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="identity.internal_unavailable",
                detail="Servicio de negocio no disponible",
            ) from exc

    def establecimientos_de(self, camarero_id: uuid.UUID) -> list[dict]:
        response = self._request("GET", f"/internal/camareros/{camarero_id}/establecimientos")
        if response.status_code != 200:
            _raise_from_response(response, "identity.internal_error")
        return response.json()

    def invitaciones_de(self, camarero_id: uuid.UUID) -> list[dict]:
        response = self._request("GET", f"/internal/camareros/{camarero_id}/invitaciones")
        if response.status_code != 200:
            _raise_from_response(response, "identity.internal_error")
        return response.json()

    def aceptar_invitacion(self, invitacion_id: uuid.UUID, camarero_id: uuid.UUID) -> dict:
        response = self._request(
            "POST",
            f"/internal/camareros/{camarero_id}/invitaciones/{invitacion_id}/aceptar",
        )
        if response.status_code != 200:
            _raise_from_response(response, "identity.internal_error")
        return response.json()

    def rechazar_invitacion(self, invitacion_id: uuid.UUID, camarero_id: uuid.UUID) -> dict:
        response = self._request(
            "POST",
            f"/internal/camareros/{camarero_id}/invitaciones/{invitacion_id}/rechazar",
        )
        if response.status_code != 200:
            _raise_from_response(response, "identity.internal_error")
        return response.json()


def _transport() -> str:
    return os.environ.get(TRANSPORT_ENV, "direct").lower()


def get_camareros_internal() -> CamarerosInternal:
    if _transport() == "http":
        return HttpCamarerosInternal(os.environ[CAMAREROS_URL_ENV])
    return DirectCamarerosInternal()


def get_negocio_internal() -> NegocioInternal:
    if _transport() == "http":
        return HttpNegocioInternal(os.environ[NEGOCIO_URL_ENV])
    return DirectNegocioInternal()
