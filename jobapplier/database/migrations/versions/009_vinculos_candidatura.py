"""Vínculo entre a candidatura aberta no navegador e a vaga do acervo.

Revision ID: 009
Revises: 008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vinculos_candidatura",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plataforma", sa.String(length=30), nullable=False),
        sa.Column("referencia", sa.String(length=100), nullable=False),
        sa.Column("vaga_id", sa.Integer(), nullable=False),
        sa.Column("origem", sa.String(length=20), server_default="referrer", nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plataforma", "referencia",
                            name="uq_vinculos_plataforma_referencia"),
    )
    op.create_index("ix_vinculos_referencia", "vinculos_candidatura", ["referencia"])
    op.create_index("ix_vinculos_vaga_id", "vinculos_candidatura", ["vaga_id"])


def downgrade() -> None:
    op.drop_index("ix_vinculos_vaga_id", table_name="vinculos_candidatura")
    op.drop_index("ix_vinculos_referencia", table_name="vinculos_candidatura")
    op.drop_table("vinculos_candidatura")
