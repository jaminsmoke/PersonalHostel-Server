"""Errores de dominio con código estable para la API /v1.

Los clientes (Bar, Commander) pueden fiarse del campo ``code`` para ramificar
lógica, en lugar de parsear el ``detail`` en español.
"""

from fastapi import HTTPException


class ApiError(HTTPException):
    """HTTPException con un código de error estable (``identity.*``)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


# Códigos canónicos (estables de cara a las apps).
VALIDATION_ERROR = "identity.validation_error"
EMAIL_ALREADY_REGISTERED = "identity.email_ya_registrado"
INVALID_CREDENTIALS = "identity.credenciales_invalidas"
CREDENTIAL_REVOKED = "identity.credential_revoked"
INVALID_TOKEN = "identity.token_invalido"
FOTO_INVALIDA = "identity.foto_invalida"
FOTO_INEXISTENTE = "identity.foto_inexistente"
PASSWORD_INCORRECTA = "identity.password_incorrecta"
NEGOCIO_EMAIL_ALREADY_REGISTERED = "identity.negocio_email_ya_registrado"
NEGOCIO_INVALID_CREDENTIALS = "identity.negocio_credenciales_invalidas"
NEGOCIO_INVALID_TOKEN = "identity.negocio_token_invalido"
ESTABLECIMIENTO_NOT_FOUND = "identity.establecimiento_no_encontrado"
LAYOUT_NOT_FOUND = "identity.layout_no_encontrado"
MEMBERSHIP_FORBIDDEN = "identity.membresia_prohibida"
MEMBERSHIP_DUPLICATE = "identity.membresia_duplicada"
CAMARERO_NOT_FOUND = "identity.camarero_no_encontrado"
QR_INVALIDO = "identity.qr_invalido"
CREDENTIAL_INACTIVE = "identity.credencial_inactiva"
INVITACION_EXPIRED = "identity.invitacion_expirada"
INVITACION_UNAUTHORIZED = "identity.invitacion_no_autorizada"
INVITACION_USED = "identity.invitacion_ya_usada"
INVITACION_NOT_FOUND = "identity.invitacion_no_encontrada"
INVITACION_DUPLICATE = "identity.invitacion_duplicada"
EMAIL_NOT_FOUND = "identity.email_no_encontrado"
PRODUCTO_NOT_FOUND = "identity.producto_no_encontrado"
SYNC_OPERATION_UNSUPPORTED = "identity.operacion_sync_no_soportada"
SYNC_OPERATION_ID_CONFLICT = "identity.operation_id_en_uso"
SYNC_CONFLICT_NOT_FOUND = "identity.conflicto_sync_no_encontrado"
SYNC_CONFLICT_RESOLVED = "identity.conflicto_sync_ya_resuelto"
SYNC_RESOLUTION_STALE = "identity.resolucion_sync_obsoleta"
NOTIFICACION_NOT_FOUND = "identity.notificacion_no_encontrada"
NON_REAL_DATA_FORBIDDEN = "identity.procedencia_no_permitida"
DATA_ORIGIN_MISMATCH = "identity.procedencia_incompatible"
ENLACE_NOT_FOUND = "identity.enlace_no_encontrado"
ENLACE_DUPLICATE = "identity.enlace_duplicado"
ENLACE_ACTIVO_EXISTENTE = "identity.enlace_activo_existente"
ENLACE_REVOCADO = "identity.enlace_revocado"
MESA_TOKEN_INVALIDO = "identity.mesa_token_invalido"
MESA_TOKEN_REVOCADO = "identity.mesa_token_revocado"
MESA_CFC_NO_ENCONTRADA = "identity.mesa_cfc_no_encontrada"
CFC_CERRADO = "identity.cfc_cerrado"
CFC_JORNADA_YA_ABIERTA = "identity.cfc_jornada_ya_abierta"
CFC_JORNADA_NO_ABIERTA = "identity.cfc_jornada_no_abierta"
CFC_PEDIDO_NO_ENCONTRADO = "identity.cfc_pedido_no_encontrado"
WEB_PRIVADA = "identity.web_privada"
FONDO_INVALIDO = "identity.fondo_invalido"
JORNADA_YA_ABIERTA = "identity.jornada_ya_abierta"
JORNADA_NO_ABIERTA = "identity.jornada_no_abierta"
SESION_NOT_FOUND = "identity.sesion_no_encontrada"
RATE_LIMITED = "identity.rate_limited"
RATE_LIMIT_UNAVAILABLE = "identity.rate_limit_unavailable"
