"""lease de outbox de email: enviando_desde + worker_id

Revision ID: 0017_outbox_lease
Revises: 0016_sesiones
Create Date: 2026-08-23

Permite recuperar filas `enviando` huérfanas tras una caída del worker.
Ambas columnas son nullable: las filas antiguas se tratan como lease vencido.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_outbox_lease"
down_revision: Union[str, None] = "0016_sesiones"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_outbox",
        sa.Column("enviando_desde", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_outbox",
        sa.Column("worker_id", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_email_outbox_lease",
        "email_outbox",
        ["estado", "enviando_desde"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_outbox_lease", table_name="email_outbox")
    op.drop_column("email_outbox", "worker_id")
    op.drop_column("email_outbox", "enviando_desde")
