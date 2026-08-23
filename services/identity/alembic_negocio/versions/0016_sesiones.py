"""sesiones de cuenta de negocio (JWT jti + refresh)

Revision ID: 0016_sesiones
Revises: 0015_cfc_inbox
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0016_sesiones"
down_revision: Union[str, None] = "0015_cfc_inbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cuentas_negocio",
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
        sa.Column("cuenta_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["cuenta_id"], ["cuentas_negocio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_hash", name="uq_sesiones_negocio_refresh_hash"),
    )
    op.create_index("ix_sesiones_cuenta_id", "sesiones", ["cuenta_id"])
    op.create_index(
        "ix_sesiones_cuenta_activas",
        "sesiones",
        ["cuenta_id"],
        postgresql_where=sa.text("revocada_en IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_sesiones_cuenta_activas", table_name="sesiones")
    op.drop_index("ix_sesiones_cuenta_id", table_name="sesiones")
    op.drop_table("sesiones")
    op.drop_column("cuentas_negocio", "sesiones_validas_desde")
