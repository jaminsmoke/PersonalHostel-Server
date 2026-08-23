"""sesiones de cuenta del profesional (JWT jti + refresh)

Revision ID: 0008_sesiones
Revises: 0007_aparecer_web_negocio
Create Date: 2026-08-22

Cada login crea una fila. El JWT lleva ``jti`` = ``sesiones.id``. El QR de
oficio (``credenciales``) no se toca. ``sesiones_validas_desde`` cubre JWT
emitidos antes de este esquema (sin ``jti``).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_sesiones"
down_revision: Union[str, None] = "0007_aparecer_web_negocio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "camareros",
        sa.Column("sesiones_validas_desde", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "sesiones",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("camarero_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_hash", sa.String(length=64), nullable=False),
        sa.Column("etiqueta", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ultimo_uso_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("refresh_expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revocacion", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["camarero_id"], ["camareros.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_hash", name="uq_sesiones_refresh_hash"),
    )
    op.create_index("ix_sesiones_camarero_id", "sesiones", ["camarero_id"])
    op.create_index(
        "ix_sesiones_camarero_activas",
        "sesiones",
        ["camarero_id"],
        postgresql_where=sa.text("revocada_en IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_sesiones_camarero_activas", table_name="sesiones")
    op.drop_index("ix_sesiones_camarero_id", table_name="sesiones")
    op.drop_table("sesiones")
    op.drop_column("camareros", "sesiones_validas_desde")
