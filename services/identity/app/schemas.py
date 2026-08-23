import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import DataOrigin, VisibleOtrosEstablecimientos


class RegistroRequest(BaseModel):
    """Datos de alta de un camarero."""

    nombre: str = Field(..., min_length=1, max_length=100, examples=["Ana"])
    apellidos: str = Field(..., min_length=1, max_length=200, examples=["García"])
    email: EmailStr = Field(..., examples=["ana@example.com"])
    telefono: str | None = Field(default=None, max_length=32, examples=["+34600000000"])
    direccion: str | None = Field(default=None, max_length=255, examples=["Calle Mayor 1"])
    ciudad: str | None = Field(default=None, max_length=100, examples=["Madrid"])
    password: str = Field(..., min_length=8, max_length=128, examples=["contraseña-mín-8"])
    nick: str | None = Field(default=None, min_length=1, max_length=40, examples=["Anita"])
    dispositivo: str | None = Field(default=None, max_length=80, examples=["web-camareros"])
    data_origin: DataOrigin = Field(
        default=DataOrigin.real,
        description="Procedencia inmutable; test/demo requieren habilitación del entorno.",
    )


class RegistroResponse(BaseModel):
    """Resultado del alta: id del camarero y payload del QR permanente."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    qr: str = Field(..., examples=["phid1:<camarero_id>:<credencial_id>:<firma-ed25519>"])
    ficha_url: str | None = Field(
        default=None, examples=["https://ficha.example/camareros?qr=phid1:..."]
    )
    data_origin: DataOrigin
    token: str = Field(..., examples=["<jwt>"])
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID


class CamareroPerfil(BaseModel):
    """Perfil público del camarero para la sesión."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    nombre: str = Field(..., examples=["Ana"])
    apellidos: str = Field(..., examples=["García"])
    email: str = Field(..., examples=["ana@example.com"])
    telefono: str | None = Field(default=None, examples=["+34600000000"])
    direccion: str | None = Field(default=None, examples=["Calle Mayor 1"])
    ciudad: str | None = Field(default=None, examples=["Madrid"])
    foto_url: str | None = Field(default=None, examples=["/v1/camareros/me/foto"])
    nick: str | None = Field(default=None, examples=["Anita"])
    data_origin: DataOrigin
    visible_otros_establecimientos: VisibleOtrosEstablecimientos = Field(
        default=VisibleOtrosEstablecimientos.nunca,
        description="Preferencia de aparecer en el directorio de otros establecimientos.",
    )
    aparecer_web_negocio: bool = Field(
        default=False,
        description="Opt-in para aparecer en la web pública de los establecimientos "
        "donde trabaja (matriz AND con el `mostrar_equipo` del local).",
    )


class PaginaPublicaUpdateRequest(BaseModel):
    """Preferencia del camarero sobre aparecer en la web pública del negocio."""

    aparecer_web_negocio: bool = Field(
        ...,
        description="true: el camarero puede aparecer en la página pública de los "
        "establecimientos donde es miembro activo.",
    )


class VisibilidadEstablecimientosUpdateRequest(BaseModel):
    """Preferencia del camarero sobre el directorio de otros establecimientos."""

    visible: VisibleOtrosEstablecimientos = Field(
        ...,
        description="siempre | solo_libre | nunca (default seguro: nunca).",
    )


class VisibilidadCamarero(BaseModel):
    """Visibilidad pública por campo (default: sensibles privados)."""

    nombre: bool = True
    apellidos: bool = True
    nick: bool = True
    email: bool = False
    telefono: bool = False
    direccion: bool = False
    ciudad: bool = False
    foto: bool = False


class VisibilidadUpdateRequest(BaseModel):
    """Actualización parcial de visibilidad (solo los campos enviados)."""

    nombre: bool | None = None
    apellidos: bool | None = None
    nick: bool | None = None
    email: bool | None = None
    telefono: bool | None = None
    direccion: bool | None = None
    ciudad: bool | None = None
    foto: bool | None = None


class CamareroFichaPublica(BaseModel):
    """Ficha pública del camarero: solo campos visibles (foto opt-in)."""

    camarero_id: uuid.UUID
    nombre: str
    apellidos: str
    nick: str | None = None
    email: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    foto_url: str | None = None


class PerfilUpdateRequest(BaseModel):
    """Campos editables de la cuenta desde Commander (no desde Bar)."""

    nick: str | None = Field(default=None, min_length=1, max_length=40, examples=["Anita"])
    direccion: str | None = Field(default=None, max_length=255, examples=["Calle Mayor 1"])
    ciudad: str | None = Field(default=None, max_length=100, examples=["Madrid"])

    @model_validator(mode="after")
    def _exige_cambio(self) -> PerfilUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos un campo para actualizar")
        return self


class LoginRequest(BaseModel):
    """Credenciales para recuperar la sesión y el QR tras reinstalar."""

    email: EmailStr = Field(..., examples=["ana@example.com"])
    password: str = Field(..., examples=["contraseña-mín-8"])
    dispositivo: str | None = Field(default=None, max_length=80, examples=["Pixel 8"])


class LoginResponse(BaseModel):
    """Sesión JWT, perfil y QR de la credencial activa."""

    token: str = Field(..., examples=["<jwt>"])
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID
    camarero: CamareroPerfil
    qr: str = Field(..., examples=["phid1:<camarero_id>:<credencial_id>:<firma-ed25519>"])
    ficha_url: str | None = Field(
        default=None, examples=["https://ficha.example/camareros?qr=phid1:..."]
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, max_length=128)


class RefreshResponse(BaseModel):
    token: str
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID


class SesionItem(BaseModel):
    id: uuid.UUID
    etiqueta: str | None = None
    creada_en: datetime
    ultimo_uso_en: datetime
    actual: bool


class RevocarSesionRequest(BaseModel):
    motivo: str | None = Field(default=None, max_length=200)


class RevocarSesionResponse(BaseModel):
    status: str = Field(..., examples=["revocada"])
    revocadas: int = Field(default=1)


class QrResponse(BaseModel):
    """Payload para pintar el QR permanente y su URL pública de ficha."""

    qr: str = Field(..., examples=["phid1:<camarero_id>:<credencial_id>:<firma-ed25519>"])
    ficha_url: str | None = Field(
        default=None, examples=["https://ficha.example/camareros?qr=phid1:..."]
    )


class RevocarRequest(BaseModel):
    """Motivo opcional de la revocación."""

    motivo: str | None = Field(default=None, max_length=500, examples=["tablet perdido"])


class RevocarResponse(BaseModel):
    """Estado tras revocar la credencial activa."""

    status: str = Field(..., examples=["revocada"])


class ErrorResponse(BaseModel):
    """Respuesta de error con código estable y mensaje en español."""

    code: str = Field(..., examples=["identity.credential_revoked"])
    detail: str | list[str] = Field(..., examples=["Clave revocada. Renueva la clave"])


class FotoResponse(BaseModel):
    """Estado de la foto de perfil tras subirla o borrarla."""

    foto_url: str | None = Field(default=None, examples=["/v1/camareros/me/foto"])


class SupresionRequest(BaseModel):
    """Confirmación (password) para ejercer el derecho de supresión."""

    password: str = Field(..., examples=["contraseña-mín-8"])


class SupresionResponse(BaseModel):
    """Resultado del borrado de la cuenta."""

    status: str = Field(..., examples=["borrada"])


class CambioPasswordRequest(BaseModel):
    """Rotación de la contraseña de acceso (camarero o negocio)."""

    password_actual: str = Field(..., examples=["contraseña-mín-8"])
    password_nueva: str = Field(..., min_length=8, max_length=128, examples=["nueva-contraseña-8"])


class CambioPasswordResponse(BaseModel):
    """Resultado del cambio de contraseña. Incluye un par de sesión nuevo."""

    status: str = Field(..., examples=["cambiada"])
    token: str
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID


class CuentaNegocioPerfil(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    nombre_mostrar: str
    tipo_establecimiento: str | None = None
    logo_url: str | None = None
    camarero_vinculado_id: uuid.UUID | None = None
    data_origin: DataOrigin


class CuentaNegocioUpdateRequest(BaseModel):
    """Actualización parcial de la organización propietaria."""

    nombre_mostrar: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("nombre_mostrar")
    @classmethod
    def _nombre_no_vacio(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("El nombre no puede estar vacío")
        return value

    @model_validator(mode="after")
    def _exige_cambio(self) -> CuentaNegocioUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos un campo para actualizar")
        return self


class RegistroNegocioRequest(BaseModel):
    nombre_mostrar: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    tipo_establecimiento: str | None = Field(
        default=None,
        pattern="^(bar|restaurante|cafeteria|pub|copas)$",
        description="Tipo de establecimiento del catálogo canónico.",
    )
    camarero_vinculado_id: uuid.UUID | None = None
    data_origin: DataOrigin = Field(
        default=DataOrigin.real,
        description="Procedencia inmutable; test/demo requieren habilitación del entorno.",
    )
    dispositivo: str | None = Field(default=None, max_length=80)


class LogoNegocioResponse(BaseModel):
    logo_url: str | None


class RegistroNegocioResponse(BaseModel):
    id: uuid.UUID
    data_origin: DataOrigin
    token: str
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID


class LoginNegocioResponse(BaseModel):
    token: str
    refresh_token: str
    expires_in: int
    sesion_id: uuid.UUID
    cuenta: CuentaNegocioPerfil


class EstablecimientoCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    tipo_establecimiento: str | None = Field(
        default=None,
        pattern="^(bar|restaurante|cafeteria|pub|copas)$",
    )


class EstablecimientoUpdateRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    tipo_establecimiento: str | None = Field(
        default=None,
        pattern="^(bar|restaurante|cafeteria|pub|copas)$",
    )
    visible_directorio: bool | None = Field(
        default=None,
        description="Opt-in para aparecer en el directorio de establecimientos.",
    )

    @field_validator("nombre")
    @classmethod
    def _nombre_no_vacio(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("El nombre no puede estar vacío")
        return value

    @model_validator(mode="after")
    def _exige_cambio(self) -> EstablecimientoUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos un campo para actualizar")
        return self


class EstablecimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo_establecimiento: str | None = None
    logo_url: str | None = None
    cuenta_negocio_id: uuid.UUID
    data_origin: DataOrigin
    visible_directorio: bool


class EstablecimientoMembresiaResponse(EstablecimientoResponse):
    rol: str


class MembresiaCreateRequest(BaseModel):
    camarero_id: uuid.UUID
    rol: str = Field(default="staff", pattern="^(dueno|staff)$")


class MembresiaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    establecimiento_id: uuid.UUID
    camarero_id: uuid.UUID
    rol: str
    estado: str


class SupresionNegocioRequest(BaseModel):
    password: str


class QrPublicKeyResponse(BaseModel):
    algorithm: str
    key_id: str
    public_key: str
    qr_prefix: str
    format: str


class QrMemberRequest(BaseModel):
    qr: str = Field(..., min_length=20, max_length=500)
    rol: str = Field(default="staff", pattern="^(dueno|staff)$")


class CamareroSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    apellidos: str
    email: str
    nick: str | None = None
    data_origin: DataOrigin


class CamareroDirectorioResponse(BaseModel):
    """Entrada del directorio de camareros para invitar.

    Sin email por privacidad: solo lo que un establecimiento necesita para
    decidir invitar. ``libre`` indica si el camarero no tiene membresía activa
    en ningún establecimiento.
    """

    id: uuid.UUID
    nombre: str
    apellidos: str
    nick: str | None = None
    foto_url: str | None = None
    libre: bool
    visibilidad: VisibleOtrosEstablecimientos


class InvitacionCreateRequest(BaseModel):
    email: EmailStr | None = Field(
        default=None,
        description="Email del camarero (flujo por email). Alternativo a camarero_id.",
    )
    camarero_id: uuid.UUID | None = Field(
        default=None,
        description="Id del camarero (flujo por directorio); el email se resuelve en servidor.",
    )
    rol: str = Field(default="staff", pattern="^(dueno|staff)$")

    @model_validator(mode="after")
    def _exige_email_o_camarero(self) -> InvitacionCreateRequest:
        if self.email is None and self.camarero_id is None:
            raise ValueError("Se requiere email o camarero_id para invitar")
        return self


class InvitacionResponse(BaseModel):
    id: uuid.UUID
    establecimiento_id: uuid.UUID
    email: str
    rol: str
    estado: str
    expira_en: datetime
    creada_en: datetime


class InvitacionAcceptResponse(BaseModel):
    invitacion_id: uuid.UUID
    membresia: MembresiaResponse


class InvitacionRechazarResponse(BaseModel):
    """Resultado del rechazo de una invitación por el camarero."""

    invitacion_id: uuid.UUID
    estado: str


class InvitacionCamareroResponse(BaseModel):
    """Invitación dirigida al camarero, con nombre del establecimiento."""

    id: uuid.UUID
    establecimiento_id: uuid.UUID
    establecimiento_nombre: str
    rol: str
    estado: str
    expira_en: datetime
    creada_en: datetime


LAYOUT_META_KEYS = frozenset({"establecimiento_id", "version", "updated_at"})


class LayoutUpdateRequest(BaseModel):
    """Snapshot opaco del layout que sube Bar.

    ``salas`` y ``mesas`` son las capas históricas requeridas (convivencia con
    el cliente actual). Cualquier clave adicional (p. ej. ``zonas``) se persiste
    y se devuelve sin validar la forma. Identity no interpreta el documento.
    """

    model_config = ConfigDict(extra="allow")

    salas: list[Any] = Field(..., min_length=0)
    mesas: list[Any] = Field(..., min_length=0)

    @model_validator(mode="after")
    def _sin_metadatos(self) -> LayoutUpdateRequest:
        extra = self.__pydantic_extra__ or {}
        choque = LAYOUT_META_KEYS.intersection(extra)
        if choque:
            nombres = ", ".join(sorted(choque))
            raise ValueError(f"No se pueden enviar metadatos del layout ({nombres})")
        return self

    def snapshot(self) -> dict[str, Any]:
        """Documento JSON a persistir, incluidas las claves extra."""
        return self.model_dump(mode="json")


class LayoutResponse(BaseModel):
    """Copia de respaldo del layout de un establecimiento.

    Además de los campos fijos, el JSON incluye el resto del documento opaco
    (p. ej. ``zonas``) tal cual se guardó.
    """

    model_config = ConfigDict(extra="allow")

    establecimiento_id: uuid.UUID
    version: int
    salas: list[Any]
    mesas: list[Any]
    updated_at: datetime


def layout_response_from_row(
    establecimiento_id: uuid.UUID,
    version: int,
    updated_at: datetime,
    documento: dict[str, Any] | None,
) -> LayoutResponse:
    """Proyecta el documento opaco sobre el DTO de respuesta (metadatos ganan)."""
    doc = dict(documento or {})
    fusionado = {
        **{clave: valor for clave, valor in doc.items() if clave not in LAYOUT_META_KEYS},
        "establecimiento_id": establecimiento_id,
        "version": version,
        "updated_at": updated_at,
    }
    return LayoutResponse.model_validate(fusionado)


class ProductoPayload(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    categoria: str = Field(..., min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=800)
    destino: str = Field(..., pattern="^(barra|cocina)$")
    precio_centimos: int = Field(..., ge=0, le=2_147_483_647)
    moneda: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    disponible: bool = True


class ProductoResponse(ProductoPayload):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    establecimiento_id: uuid.UUID
    data_origin: DataOrigin
    revision: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class CatalogoResponse(BaseModel):
    establecimiento_id: uuid.UUID
    revision: int
    server_time: datetime
    productos: list[ProductoResponse]


class OperacionSyncRequest(BaseModel):
    operation_id: uuid.UUID
    device_id: str = Field(..., min_length=1, max_length=200)
    aggregate_type: str = Field(default="producto", min_length=1, max_length=50)
    aggregate_id: uuid.UUID
    action: str = Field(..., pattern="^(crear|actualizar|archivar)$")
    base_revision: int = Field(default=0, ge=0)
    base_snapshot: dict[str, Any] | None = None
    payload: ProductoPayload | None = None
    client_created_at: datetime


class OperacionSyncResponse(BaseModel):
    operation_id: uuid.UUID
    estado: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    action: str
    base_revision: int
    global_revision: int | None = None
    result_snapshot: dict[str, Any] | None = None
    conflict_id: uuid.UUID | None = None
    client_created_at: datetime
    server_received_at: datetime


class CambioSyncResponse(BaseModel):
    revision: int
    operation_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    action: str
    snapshot: dict[str, Any]


class CambiosSyncResponse(BaseModel):
    establecimiento_id: uuid.UUID
    desde: int
    revision_actual: int
    cambios: list[CambioSyncResponse]


class ConflictoSyncResponse(BaseModel):
    id: uuid.UUID
    operation_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    action: str
    base_revision: int
    canonical_revision: int
    base_snapshot: dict[str, Any] | None = None
    canonical_snapshot: dict[str, Any] | None = None
    proposed_snapshot: dict[str, Any] | None = None
    estado: str
    device_id: str
    client_created_at: datetime
    server_received_at: datetime
    created_at: datetime
    resolved_at: datetime | None = None


class ResolverConflictoRequest(BaseModel):
    decision: str = Field(..., pattern="^(aceptar|rechazar)$")
    expected_revision: int = Field(..., ge=0)


class NotificacionNegocioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    establecimiento_id: uuid.UUID
    conflicto_id: uuid.UUID | None = None
    tipo: str
    titulo: str
    mensaje: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None = None


class EnlacePublicoCreateRequest(BaseModel):
    """Alta de un enlace público para un establecimiento."""

    tipo: str = Field(..., pattern="^(web|carta)$")
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern="^[a-z0-9-]+$")


class EnlacePublicoRotarRequest(BaseModel):
    """Slug opcional para sustituir un enlace conservando su tipo."""

    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern="^[a-z0-9-]+$")


class EnlacePublicoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    establecimiento_id: uuid.UUID
    tipo: str
    slug: str
    estado: str
    expira_en: datetime | None = None
    url_publica: str | None = None


class EnlacePublicoResolucion(BaseModel):
    """Resolución pública de un enlace: tipo + destino (sin PII)."""

    tipo: str
    establecimiento_id: uuid.UUID


MAX_MESAS_CFC = 500


class MesaCfcItemRequest(BaseModel):
    """Una mesa del conjunto que Bar envía (UUID estable + etiqueta UX)."""

    mesa_uuid: uuid.UUID
    etiqueta: str = Field(..., min_length=1, max_length=40)

    @field_validator("etiqueta")
    @classmethod
    def _etiqueta_no_vacia(cls, value: str) -> str:
        limpio = value.strip()
        if not limpio:
            raise ValueError("etiqueta vacía")
        return limpio


class MesasCfcSyncRequest(BaseModel):
    """Conjunto completo de mesas públicas del establecimiento."""

    mesas: list[MesaCfcItemRequest] = Field(..., max_length=MAX_MESAS_CFC)

    @field_validator("mesas")
    @classmethod
    def _uuids_unicos(cls, value: list[MesaCfcItemRequest]) -> list[MesaCfcItemRequest]:
        ids = [item.mesa_uuid for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("mesa_uuid duplicado en el conjunto")
        return value


class MesaCfcResponse(BaseModel):
    mesa_uuid: uuid.UUID
    etiqueta: str
    estado: str
    url_publica: str | None = None


class MesaCfcPublicaResponse(BaseModel):
    """Resolución pública del token de mesa (sin carta ni pedidos)."""

    establecimiento_id: uuid.UUID
    establecimiento_nombre: str
    mesa_uuid: uuid.UUID
    etiqueta: str
    admite_pedidos: bool = False
    bar_en_linea: bool = False


class PedidoCfcLineaRequest(BaseModel):
    producto_id: uuid.UUID
    cantidad: int = Field(..., ge=1, le=99)


class PedidoCfcCreateRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=64)
    lineas: list[PedidoCfcLineaRequest] = Field(..., min_length=1, max_length=50)


class PedidoCfcLinea(BaseModel):
    producto_id: uuid.UUID
    nombre: str
    cantidad: int
    precio_centimos: int
    destino: str


class PedidoCfcResponse(BaseModel):
    id: uuid.UUID
    mesa_uuid: uuid.UUID
    etiqueta: str
    estado: str
    seq: int
    lineas: list[PedidoCfcLinea]
    total_centimos: int
    creado_en: datetime


class PedidoCfcAckRequest(BaseModel):
    decision: Literal["aceptado", "rechazado"]


class PedidosCfcListaResponse(BaseModel):
    pedidos: list[PedidoCfcResponse]
    cursor: int


class JornadaCfcResponse(BaseModel):
    id: uuid.UUID
    establecimiento_id: uuid.UUID
    abierta_en: datetime
    ultimo_heartbeat: datetime
    cerrada_en: datetime | None = None
    bar_en_linea: bool = True


class ProductoCartaCfc(BaseModel):
    id: uuid.UUID
    nombre: str
    precio_centimos: int
    categoria: str
    destino: str


class CartaCfcResponse(BaseModel):
    establecimiento_id: uuid.UUID
    nombre: str
    admite_pedidos: bool
    bar_en_linea: bool
    productos: list[ProductoCartaCfc]


class CuentaCfcResponse(BaseModel):
    mesa_uuid: uuid.UUID
    etiqueta: str
    admite_pedidos: bool
    bar_en_linea: bool
    lineas: list[PedidoCfcLinea]
    total_centimos: int


class ProductoCartaPublica(BaseModel):
    """Producto visible en la carta pública (sin revisión ni procedencia)."""

    model_config = ConfigDict(exclude_none=True)

    nombre: str
    precio_centimos: int
    moneda: str
    destino: str
    descripcion: str | None = None


class CategoriaCartaPublica(BaseModel):
    nombre: str
    productos: list[ProductoCartaPublica]


class CartaPublicaResponse(BaseModel):
    establecimiento_id: uuid.UUID
    nombre: str
    categorias: list[CategoriaCartaPublica]


def _minutos(hhmm: str) -> int:
    """HH:MM → minutos desde medianoche (validación de orden y solapamientos)."""

    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


class TurnoHorario(BaseModel):
    """Intervalo de apertura/cierre en HH:MM (mismo día, sin cruce de medianoche)."""

    abre: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", examples=["10:00"])
    cierra: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", examples=["16:00"])

    @model_validator(mode="after")
    def _turno_valido(self) -> TurnoHorario:
        if _minutos(self.cierra) <= _minutos(self.abre):
            raise ValueError("El turno debe abrir antes de cerrar")
        return self


class HorarioDia(BaseModel):
    """Un día de la semana (0=lunes … 6=domingo). ``cerrado`` sin turnos."""

    dia_semana: int = Field(..., ge=0, le=6, examples=[0])
    cerrado: bool = False
    turnos: list[TurnoHorario] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _dia_valido(self) -> HorarioDia:
        if self.cerrado:
            if self.turnos:
                raise ValueError("Un día cerrado no puede tener turnos")
            return self
        if not self.turnos:
            raise ValueError("Un día abierto requiere al menos un turno")
        turnos = sorted(self.turnos, key=lambda t: _minutos(t.abre))
        for anterior, actual in zip(turnos, turnos[1:], strict=False):
            if _minutos(actual.abre) < _minutos(anterior.cierra):
                raise ValueError("Los turnos de un mismo día no pueden solaparse")
        return self


class HorarioUpdateRequest(BaseModel):
    """Reemplazo completo del horario semanal de un establecimiento."""

    dias: list[HorarioDia] = Field(..., max_length=7)

    @model_validator(mode="after")
    def _dias_no_repetidos(self) -> HorarioUpdateRequest:
        if len({d.dia_semana for d in self.dias}) != len(self.dias):
            raise ValueError("No se puede repetir un día de la semana")
        return self


class HorarioResponse(BaseModel):
    """Horario completo de un establecimiento (ordenado lunes→domingo)."""

    establecimiento_id: uuid.UUID
    dias: list[HorarioDia] = Field(default_factory=list)
    updated_at: datetime | None = None


class PerfilNegocioPublico(BaseModel):
    """Bloque «quién somos» de la web pública del local."""

    eslogan: str | None = None
    descripcion: str | None = None
    direccion: str | None = None
    ciudad: str | None = None


class ContactoNegocioPublico(BaseModel):
    """Bloque de contacto de la web pública del local."""

    telefono: str | None = None
    email_contacto: str | None = None
    web: str | None = None
    redes: dict = Field(default_factory=dict)


class HeroNegocioPublico(BaseModel):
    """Imagen de portada de la web pública del local."""

    url: str


class ImagenGaleriaPublica(BaseModel):
    """Imagen de la galería de la web pública del local."""

    id: uuid.UUID
    url: str


class AbiertoAhora(BaseModel):
    """Estado actual del local respecto a su horario (en el huso del local)."""

    abierto: bool
    proximo_cambio: datetime | None = None


class MiembroEquipoPublico(BaseModel):
    """Miembro del equipo visible en la web pública (matriz AND)."""

    camarero_id: uuid.UUID
    nombre: str
    apellidos: str
    nick: str | None = None
    foto_url: str | None = None
    rol: str


class FondoPublico(BaseModel):
    """Slot de fondo en la web pública."""

    fuente: Literal["catalogo", "upload", "hero"]
    id: str | None = None
    url: str


class WebNegocioPublica(BaseModel):
    """Datos de la web pública del establecimiento (ficha + carta)."""

    establecimiento_id: uuid.UUID
    nombre: str
    tipo_establecimiento: str | None = None
    logo_url: str | None = None
    organizacion_nombre: str
    plantilla: str = "estate_hospitality"
    color_primario: str | None = None
    perfil: PerfilNegocioPublico | None = None
    contacto: ContactoNegocioPublico | None = None
    hero: HeroNegocioPublico | None = None
    galeria: list[ImagenGaleriaPublica] = Field(default_factory=list)
    abierto_ahora: AbiertoAhora | None = None
    horario: list[HorarioDia] | None = None
    equipo: list[MiembroEquipoPublico] = Field(default_factory=list)
    categorias: list[CategoriaCartaPublica] = Field(default_factory=list)
    fondos: dict[str, FondoPublico] = Field(default_factory=dict)


class PerfilEstablecimientoUpdateRequest(BaseModel):
    """Campos editables del perfil público del establecimiento (PATCH parcial)."""

    eslogan: str | None = Field(default=None, max_length=140)
    descripcion: str | None = None
    direccion: str | None = Field(default=None, max_length=255)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=32)
    email_contacto: EmailStr | None = None
    web: str | None = Field(default=None, max_length=255)
    redes: dict[str, str] | None = None
    tz: str | None = Field(default=None, max_length=64)
    plantilla: str | None = Field(default=None, max_length=50)
    color_primario: str | None = Field(default=None, max_length=20)
    web_publica: bool | None = None
    mostrar_equipo: bool | None = None

    @model_validator(mode="after")
    def _algo_cambia(self) -> PerfilEstablecimientoUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos un campo para actualizar")
        return self


class PerfilEstablecimientoResponse(BaseModel):
    """Perfil público del establecimiento (gestión con la cuenta de negocio)."""

    establecimiento_id: uuid.UUID
    eslogan: str | None = None
    descripcion: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    telefono: str | None = None
    email_contacto: str | None = None
    web: str | None = None
    redes: dict = Field(default_factory=dict)
    tz: str = "Europe/Madrid"
    plantilla: str = "estate_hospitality"
    color_primario: str | None = None
    web_publica: bool = True
    mostrar_equipo: bool = False
    hero_url: str | None = None


class ImagenEstablecimientoResponse(BaseModel):
    """Imagen de la galería del establecimiento."""

    id: uuid.UUID
    establecimiento_id: uuid.UUID
    url: str
    mimetype: str
    size: int
    orden: int
    creada_en: datetime


class CatalogoFondoItem(BaseModel):
    """Miniatura de un fondo Estate por sección."""

    id: str
    seccion: str
    url: str


class FondoAsignado(BaseModel):
    """Slot de fondo resuelto (gestión o público)."""

    fuente: Literal["catalogo", "upload", "hero"]
    id: str | None = None
    url: str


class FondoSlotCatalogo(BaseModel):
    """Asignación de un fondo de catálogo a un slot."""

    fuente: Literal["catalogo"]
    id: str


class FondosUpdateRequest(BaseModel):
    """PUT parcial: catálogo o ``null`` para volver al default."""

    model_config = ConfigDict(extra="forbid")

    inicio: FondoSlotCatalogo | None = None
    horario: FondoSlotCatalogo | None = None
    carta: FondoSlotCatalogo | None = None
    equipo: FondoSlotCatalogo | None = None
    contacto: FondoSlotCatalogo | None = None

    @model_validator(mode="after")
    def _algo_cambia(self) -> FondosUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos una sección para actualizar")
        return self


class FondosAsignadosResponse(BaseModel):
    """Asignación actual de fondos por sección."""

    inicio: FondoAsignado
    horario: FondoAsignado
    carta: FondoAsignado
    equipo: FondoAsignado
    contacto: FondoAsignado


class JornadaIniciarRequest(BaseModel):
    """Establecimiento donde el camarero abre su jornada."""

    establecimiento_id: uuid.UUID


class JornadaResponse(BaseModel):
    """Intervalo de jornada (abierta o cerrada)."""

    id: uuid.UUID
    camarero_id: uuid.UUID
    establecimiento_id: uuid.UUID
    inicio: datetime
    fin: datetime | None = None


class ResumenPorEstablecimiento(BaseModel):
    """Agregado de oficio de un establecimiento en la ventana."""

    establecimiento_id: uuid.UUID
    horas_segundos: int
    mesas_servidas: int


class ResumenOficioResponse(BaseModel):
    """Resumen del libro de oficio del camarero en una ventana."""

    desde: datetime
    hasta: datetime
    horas_segundos: int
    mesas_servidas: int
    por_establecimiento: list[ResumenPorEstablecimiento] = Field(default_factory=list)


class ServicioRegistroRequest(BaseModel):
    """Evento de servicio que registra Bar (idempotente por ``evento_id``)."""

    establecimiento_id: uuid.UUID
    camarero_id: uuid.UUID
    evento_id: str = Field(..., min_length=1, max_length=64)
    tipo: str = Field(default="mesa_servida", max_length=50)
    cantidad: int = Field(default=1, ge=1)


class ServicioRegistroResponse(BaseModel):
    """Resultado del registro de un evento de servicio."""

    id: uuid.UUID
    camarero_id: uuid.UUID
    establecimiento_id: uuid.UUID
    evento_id: str
    tipo: str
    cantidad: int
    duplicado: bool
