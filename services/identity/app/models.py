import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import CamareroBase, NegocioBase


class CredencialEstado(str, enum.Enum):
    activa = "activa"
    revocada = "revocada"


class MembresiaRol(str, enum.Enum):
    dueno = "dueno"
    staff = "staff"


class MembresiaEstado(str, enum.Enum):
    activa = "activa"
    revocada = "revocada"


class InvitacionEstado(str, enum.Enum):
    pendiente = "pendiente"
    aceptada = "aceptada"
    revocada = "revocada"
    rechazada = "rechazada"
    expirada = "expirada"


TIPOS_ESTABLECIMIENTO = ("bar", "restaurante", "cafeteria", "pub", "copas")


class EmailOutboxEstado(str, enum.Enum):
    pendiente = "pendiente"
    enviando = "enviando"
    enviado = "enviado"
    fallido = "fallido"


class ProductoDestino(str, enum.Enum):
    barra = "barra"
    cocina = "cocina"


class EnlaceTipo(str, enum.Enum):
    """Tipos de enlace público (VARCHAR; crece sin enum de Postgres).

    ``web`` es el canónico de la web del local. ``ficha_negocio`` queda como
    valor residual de lectura (GET); ya no se acepta en POST.
    """

    web = "web"
    carta = "carta"
    ficha_negocio = "ficha_negocio"


class EnlaceEstado(str, enum.Enum):
    activo = "activo"
    revocado = "revocado"


class SyncAccion(str, enum.Enum):
    crear = "crear"
    actualizar = "actualizar"
    archivar = "archivar"


class SyncEstado(str, enum.Enum):
    aplicada = "aplicada"
    conflicto = "conflicto"
    rechazada = "rechazada"


class ConflictoEstado(str, enum.Enum):
    pendiente = "pendiente"
    aceptado = "aceptado"
    rechazado = "rechazado"


class DataOrigin(str, enum.Enum):
    """Procedencia inmutable de una entidad canónica."""

    real = "real"
    test = "test"
    demo = "demo"


# ── Visibilidad pública del perfil ────────────────────────────────────────

VISIBILITY_FIELDS = (
    "nombre",
    "apellidos",
    "nick",
    "email",
    "telefono",
    "direccion",
    "ciudad",
    "foto",
)

DEFAULT_VISIBILIDAD = {
    "nombre": True,
    "apellidos": True,
    "nick": True,
    "email": False,
    "telefono": False,
    "direccion": False,
    "ciudad": False,
    "foto": False,
}


class VisibleOtrosEstablecimientos(str, enum.Enum):
    """Preferencia del camarero sobre aparecer en el directorio de otros
    establecimientos (para invitación). Default seguro: nunca.

    Se persiste como string acotado (no enum de Postgres) para poder crecer
    sin migración, igual que ``EnlaceTipo``.
    """

    siempre = "siempre"
    solo_libre = "solo_libre"
    nunca = "nunca"


_VISIBILIDAD_SQL_DEFAULT = (
    '\'{"nombre": true, "apellidos": true, "nick": true, '
    '"email": false, "telefono": false, "direccion": false, '
    '"ciudad": false, "foto": false}\'::jsonb'
)


# ── BD de profesionales ────────────────────────────────────────────────────


class AppConfig(CamareroBase):
    __tablename__ = "app_config"

    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Camarero(CamareroBase):
    __tablename__ = "camareros"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(200), nullable=False)
    nick: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    telefono: Mapped[str | None] = mapped_column(String(32), unique=True)
    direccion: Mapped[str | None] = mapped_column(String(255))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255))
    foto_clave: Mapped[str | None] = mapped_column(String(255))
    foto_mimetype: Mapped[str | None] = mapped_column(String(64))
    foto_size: Mapped[int | None] = mapped_column(Integer)
    foto_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visibilidad: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: dict(DEFAULT_VISIBILIDAD),
        server_default=text(_VISIBILIDAD_SQL_DEFAULT),
    )
    visible_otros_establecimientos: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=VisibleOtrosEstablecimientos.nunca.value,
        server_default=VisibleOtrosEstablecimientos.nunca.value,
    )
    aparecer_web_negocio: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    sesiones_validas_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    credenciales: Mapped[list[Credencial]] = relationship(
        back_populates="camarero", cascade="all, delete-orphan"
    )
    sesiones: Mapped[list[SesionCamarero]] = relationship(
        back_populates="camarero", cascade="all, delete-orphan"
    )
    jornadas: Mapped[list[Jornada]] = relationship(
        back_populates="camarero", cascade="all, delete-orphan"
    )
    servicios: Mapped[list[Servicio]] = relationship(
        back_populates="camarero", cascade="all, delete-orphan"
    )

    @property
    def foto_url(self) -> str | None:
        """URL relativa de la foto de perfil, o None si no hay."""
        if not self.foto_clave:
            return None
        return "/v1/camareros/me/foto"

    def campo_visible(self, field: str) -> bool:
        """True si el campo es visible en la ficha pública (default seguro)."""
        vis = self.visibilidad or {}
        return bool(vis.get(field, DEFAULT_VISIBILIDAD.get(field, False)))


class Credencial(CamareroBase):
    __tablename__ = "credenciales"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    camarero_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("camareros.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secreto: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    estado: Mapped[CredencialEstado] = mapped_column(
        Enum(CredencialEstado, name="credencial_estado"), nullable=False
    )
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revocacion: Mapped[str | None] = mapped_column(String(500))

    camarero: Mapped[Camarero] = relationship(back_populates="credenciales")


class SesionCamarero(CamareroBase):
    """Sesión de cuenta HTTP del profesional (distinta de la credencial QR)."""

    __tablename__ = "sesiones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    camarero_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("camareros.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    etiqueta: Mapped[str | None] = mapped_column(String(80))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_uso_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    refresh_expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revocacion: Mapped[str | None] = mapped_column(String(200))

    camarero: Mapped[Camarero] = relationship(back_populates="sesiones")


class Jornada(CamareroBase):
    """Intervalo de jornada de un camarero en un establecimiento.

    ``establecimiento_id`` es un UUID plano (la entidad vive en la BD de
    negocio); la validación de membresía la hace el servicio de negocio antes
    de dejar registrar el intervalo.
    """

    __tablename__ = "jornadas"
    __table_args__ = (
        CheckConstraint("fin IS NULL OR fin >= inicio", name="ck_jornadas_intervalo"),
        Index("ix_jornadas_camarero_ventana", "camarero_id", "inicio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    camarero_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("camareros.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    camarero: Mapped[Camarero] = relationship(back_populates="jornadas")


class Servicio(CamareroBase):
    """Evento bruto de servicio (p. ej. «mesa servida») por camarero y
    establecimiento. Agregable por período para la ficha de oficio.
    ``evento_id`` es la clave de idempotencia que envía Bar.
    """

    __tablename__ = "servicios"
    __table_args__ = (
        UniqueConstraint(
            "establecimiento_id", "evento_id", name="uq_servicios_establecimiento_evento"
        ),
        CheckConstraint("cantidad > 0", name="ck_servicios_cantidad_positiva"),
        Index("ix_servicios_camarero_ventana", "camarero_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    camarero_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("camareros.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    evento_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="mesa_servida")
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camarero: Mapped[Camarero] = relationship(back_populates="servicios")


# ── BD de negocio ──────────────────────────────────────────────────────────


class CuentaNegocio(NegocioBase):
    __tablename__ = "cuentas_negocio"
    __table_args__ = (
        CheckConstraint(
            "tipo_establecimiento IS NULL OR tipo_establecimiento IN "
            "('bar', 'restaurante', 'cafeteria', 'pub', 'copas')",
            name="ck_cuentas_tipo_establecimiento",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_mostrar: Mapped[str] = mapped_column(String(200), nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    tipo_establecimiento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logo_clave: Mapped[str | None] = mapped_column(String(255))
    logo_mimetype: Mapped[str | None] = mapped_column(String(64))
    logo_size: Mapped[int | None] = mapped_column(Integer)
    logo_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # UUID plano: la FK real apunta a la BD de profesionales (otro servicio).
    camarero_vinculado_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    sesiones_validas_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    establecimientos: Mapped[list[Establecimiento]] = relationship(
        back_populates="cuenta_negocio", cascade="all, delete-orphan"
    )
    invitaciones: Mapped[list[Invitacion]] = relationship(
        back_populates="cuenta_negocio", cascade="all, delete-orphan"
    )
    sesiones: Mapped[list[SesionNegocio]] = relationship(
        back_populates="cuenta", cascade="all, delete-orphan"
    )

    @property
    def logo_url(self) -> str | None:
        """URL relativa del logo del negocio, o None si no hay."""
        if not self.logo_clave:
            return None
        return "/v1/auth/negocio/me/logo"


class SesionNegocio(NegocioBase):
    """Sesión de cuenta HTTP de la organización (distinta del QR de oficio)."""

    __tablename__ = "sesiones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cuentas_negocio.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    etiqueta: Mapped[str | None] = mapped_column(String(80))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_uso_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    refresh_expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revocacion: Mapped[str | None] = mapped_column(String(200))

    cuenta: Mapped[CuentaNegocio] = relationship(back_populates="sesiones")


class Establecimiento(NegocioBase):
    __tablename__ = "establecimientos"
    __table_args__ = (
        CheckConstraint(
            "tipo_establecimiento IS NULL OR tipo_establecimiento IN "
            "('bar', 'restaurante', 'cafeteria', 'pub', 'copas')",
            name="ck_establecimientos_tipo_establecimiento",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_establecimiento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    visible_directorio: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    logo_clave: Mapped[str | None] = mapped_column(String(255))
    logo_mimetype: Mapped[str | None] = mapped_column(String(64))
    logo_size: Mapped[int | None] = mapped_column(Integer)
    logo_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    cuenta_negocio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cuentas_negocio.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    sync_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    cuenta_negocio: Mapped[CuentaNegocio] = relationship(back_populates="establecimientos")
    membresias: Mapped[list[Membresia]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    invitaciones: Mapped[list[Invitacion]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    layout: Mapped[LayoutEstablecimiento | None] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    productos: Mapped[list[ProductoCatalogo]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    enlaces: Mapped[list[EnlacePublico]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    mesas_cfc: Mapped[list[MesaCfc]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    jornadas_cfc: Mapped[list[JornadaCfc]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    pedidos_cfc: Mapped[list[PedidoCfc]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    horarios: Mapped[list[HorarioEstablecimiento]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    perfil: Mapped[PerfilEstablecimiento | None] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )
    imagenes: Mapped[list[ImagenEstablecimiento]] = relationship(
        back_populates="establecimiento", cascade="all, delete-orphan"
    )

    @property
    def tipo_efectivo(self) -> str | None:
        """Tipo propio o default legado de la organización."""
        return self.tipo_establecimiento or self.cuenta_negocio.tipo_establecimiento

    @property
    def logo_efectivo_clave(self) -> str | None:
        return self.logo_clave or self.cuenta_negocio.logo_clave

    @property
    def logo_efectivo_mimetype(self) -> str | None:
        if self.logo_clave:
            return self.logo_mimetype
        return self.cuenta_negocio.logo_mimetype

    @property
    def logo_url(self) -> str | None:
        if not self.logo_efectivo_clave:
            return None
        return f"/v1/establecimientos/{self.id}/logo"


class PerfilEstablecimiento(NegocioBase):
    """Perfil público de la web del establecimiento (1:1 con ``establecimientos``).

    Campos de marketing y configuración de la superficie pública (plantilla,
    rebranding y visibilidad). No toca el modelo operativo del catálogo/layout:
    vive en su propia tabla para no interferir con ``sync_revision``.
    """

    __tablename__ = "perfiles_establecimiento"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    eslogan: Mapped[str | None] = mapped_column(String(140))
    descripcion: Mapped[str | None] = mapped_column(Text)
    direccion: Mapped[str | None] = mapped_column(String(255))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    telefono: Mapped[str | None] = mapped_column(String(32))
    email_contacto: Mapped[str | None] = mapped_column(String(320))
    web: Mapped[str | None] = mapped_column(String(255))
    redes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    tz: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Europe/Madrid", server_default="Europe/Madrid"
    )
    hero_clave: Mapped[str | None] = mapped_column(String(255))
    hero_mimetype: Mapped[str | None] = mapped_column(String(64))
    hero_size: Mapped[int | None] = mapped_column(Integer)
    hero_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plantilla: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="estate_hospitality",
        server_default="estate_hospitality",
    )
    color_primario: Mapped[str | None] = mapped_column(String(20))
    web_publica: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    mostrar_equipo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    fondos: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="perfil")


class ImagenEstablecimiento(NegocioBase):
    """Imagen de la galería del establecimiento (branding de su web).

    Almacenada en el mismo storage de fotos (``app.storage``) con una clave por
    imagen; ``uso`` distingue galería (``galeria``) de fondos de sección
    (``fondo_<slot>``). El hero clásico vive en ``perfiles_establecimiento``.
    """

    __tablename__ = "imagenes_establecimiento"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clave: Mapped[str] = mapped_column(String(255), nullable=False)
    mimetype: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    uso: Mapped[str] = mapped_column(
        String(20), nullable=False, default="galeria", server_default="galeria"
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="imagenes")


class ProductoCatalogo(NegocioBase):
    __tablename__ = "productos_catalogo"
    __table_args__ = (
        CheckConstraint("precio_centimos >= 0", name="ck_producto_precio_no_negativo"),
        CheckConstraint("revision > 0", name="ck_producto_revision_positiva"),
        Index(
            "ix_productos_catalogo_activos",
            "establecimiento_id",
            "destino",
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    data_origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"),
        nullable=False,
        default=DataOrigin.real,
        server_default=DataOrigin.real.value,
        index=True,
    )
    categoria: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    destino: Mapped[ProductoDestino] = mapped_column(
        Enum(ProductoDestino, name="producto_destino"), nullable=False
    )
    precio_centimos: Mapped[int] = mapped_column(Integer, nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    disponible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="productos")


class HorarioEstablecimiento(NegocioBase):
    """Horario semanal de un establecimiento (fuente canónica para la web).

    Un día por fila (lunes=0 … domingo=6). ``cerrado`` marca días sin servicio;
    ``turnos`` guarda los intervalos ``{abre, cierra}`` en HH:MM como JSON.
    La validación de forma e invariantes (orden, solapamientos) vive en la capa
    API (Pydantic), no en la BD.
    """

    __tablename__ = "horarios_establecimiento"
    __table_args__ = (
        CheckConstraint("dia_semana BETWEEN 0 AND 6", name="ck_horarios_dia_semana"),
        UniqueConstraint(
            "establecimiento_id",
            "dia_semana",
            name="uq_horarios_establecimiento_dia",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    cerrado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    turnos: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="horarios")


class EnlacePublico(NegocioBase):
    """Enlace público revocable (ficha de negocio, carta, futuros compartibles).

    Público por diseño: sin firma; se resuelve por ``slug`` opaco y se revoca
    con un toggle. ``tipo``/``estado`` son strings acotados validados en la API
    (no enums de Postgres) para poder crecer sin migración.
    """

    __tablename__ = "enlaces_publicos"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_enlaces_publicos_slug"),
        Index(
            "ix_enlaces_publicos_activos",
            "establecimiento_id",
            "tipo",
            unique=True,
            postgresql_where=text("estado = 'activo'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EnlaceEstado.activo.value,
        server_default=EnlaceEstado.activo.value,
    )
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="enlaces")


class MesaCfc(NegocioBase):
    """Mesa pública CFC: UUID familiar + token opaco (hash + SecretBox)."""

    __tablename__ = "mesas_cfc"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_mesas_cfc_token_hash"),
        Index(
            "uq_mesas_cfc_activa",
            "establecimiento_id",
            "mesa_uuid",
            unique=True,
            postgresql_where=text("estado = 'activo'"),
        ),
        Index("ix_mesas_cfc_establecimiento_estado", "establecimiento_id", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mesa_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    etiqueta: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_protegido: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EnlaceEstado.activo.value,
        server_default=EnlaceEstado.activo.value,
    )
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="mesas_cfc")


class JornadaCfc(NegocioBase):
    """Jornada de admisión CFC del local (no es el oficio del camarero)."""

    __tablename__ = "jornadas_cfc"
    __table_args__ = (
        Index(
            "uq_jornadas_cfc_abierta",
            "establecimiento_id",
            unique=True,
            postgresql_where=text("cerrada_en IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    abierta_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="jornadas_cfc")
    pedidos: Mapped[list[PedidoCfc]] = relationship(back_populates="jornada")


class PedidoCfc(NegocioBase):
    """Pedido anónimo de mesa: snapshot de líneas y cola durable para Bar."""

    __tablename__ = "pedidos_cfc"
    __table_args__ = (
        UniqueConstraint(
            "establecimiento_id", "idempotency_key", name="uq_pedidos_cfc_idempotencia"
        ),
        UniqueConstraint("establecimiento_id", "seq", name="uq_pedidos_cfc_seq"),
        Index("ix_pedidos_cfc_establecimiento_estado", "establecimiento_id", "estado"),
        Index("ix_pedidos_cfc_jornada_mesa", "jornada_id", "mesa_uuid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jornada_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jornadas_cfc.id", ondelete="CASCADE"),
        nullable=False,
    )
    mesa_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    etiqueta_snapshot: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    lineas: Mapped[list] = mapped_column(JSONB, nullable=False)
    total_centimos: Mapped[int] = mapped_column(Integer, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="pedidos_cfc")
    jornada: Mapped[JornadaCfc] = relationship(back_populates="pedidos")


class OperacionSync(NegocioBase):
    __tablename__ = "operaciones_sync"
    __table_args__ = (
        Index(
            "ix_operaciones_sync_change_feed",
            "establecimiento_id",
            "global_revision",
            postgresql_where=text("global_revision IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[SyncAccion] = mapped_column(Enum(SyncAccion, name="sync_accion"), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    base_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    client_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    estado: Mapped[SyncEstado] = mapped_column(Enum(SyncEstado, name="sync_estado"), nullable=False)
    global_revision: Mapped[int | None] = mapped_column(BigInteger)
    result_snapshot: Mapped[dict | None] = mapped_column(JSONB)


class ConflictoSync(NegocioBase):
    __tablename__ = "conflictos_sync"
    __table_args__ = (
        Index(
            "ix_conflictos_sync_pendientes",
            "establecimiento_id",
            "created_at",
            postgresql_where=text("estado = 'pendiente'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    operacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("operaciones_sync.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canonical_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    base_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    canonical_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    proposed_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    estado: Mapped[ConflictoEstado] = mapped_column(
        Enum(ConflictoEstado, name="conflicto_estado"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class NotificacionNegocio(NegocioBase):
    __tablename__ = "notificaciones_negocio"
    __table_args__ = (
        Index(
            "ix_notificaciones_negocio_no_leidas",
            "establecimiento_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conflicto_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conflictos_sync.id", ondelete="SET NULL")
    )
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensaje: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LayoutEstablecimiento(NegocioBase):
    """Copia de respaldo (DR) del layout del mapa: documento JSON opaco tal cual
    lo serializa Bar. Identity no interpreta el layout; solo lo guarda y lo
    devuelve. Fuente de verdad: Bar. Una fila por establecimiento.
    """

    __tablename__ = "layouts_establecimiento"

    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    documento: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="layout")


class Membresia(NegocioBase):
    __tablename__ = "membresias"
    __table_args__ = (
        UniqueConstraint(
            "establecimiento_id", "camarero_id", name="uq_membresia_establecimiento_camarero"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # UUID plano: el camarero vive en la BD de profesionales (otro servicio).
    camarero_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    rol: Mapped[MembresiaRol] = mapped_column(
        Enum(MembresiaRol, name="membresia_rol"), nullable=False
    )
    estado: Mapped[MembresiaEstado] = mapped_column(
        Enum(MembresiaEstado, name="membresia_estado"), nullable=False
    )
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="membresias")


class Invitacion(NegocioBase):
    __tablename__ = "invitaciones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    establecimiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("establecimientos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cuenta_negocio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cuentas_negocio.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_objetivo: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    rol: Mapped[MembresiaRol] = mapped_column(
        Enum(MembresiaRol, name="membresia_rol"), nullable=False
    )
    estado: Mapped[InvitacionEstado] = mapped_column(
        Enum(InvitacionEstado, name="invitacion_estado"), nullable=False
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aceptada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    establecimiento: Mapped[Establecimiento] = relationship(back_populates="invitaciones")
    cuenta_negocio: Mapped[CuentaNegocio] = relationship(back_populates="invitaciones")
    outbox: Mapped[list[EmailOutbox]] = relationship(
        back_populates="invitacion", cascade="all, delete-orphan"
    )


class EmailOutbox(NegocioBase):
    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    invitacion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invitaciones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    destinatario: Mapped[str] = mapped_column(String(320), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    estado: Mapped[EmailOutboxEstado] = mapped_column(
        Enum(EmailOutboxEstado, name="email_outbox_estado"), nullable=False
    )
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(String(1000))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviando_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(80))

    invitacion: Mapped[Invitacion | None] = relationship(back_populates="outbox")
