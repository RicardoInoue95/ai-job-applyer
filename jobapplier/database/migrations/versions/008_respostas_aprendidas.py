"""Banco de respostas aprendidas.

Revision ID: 008
Revises: 007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "respostas_aprendidas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chave", sa.String(length=400), nullable=False),
        sa.Column("escopo", sa.String(length=10), server_default="global", nullable=False),
        sa.Column("empresa", sa.String(length=200), server_default="", nullable=False),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=False),
        sa.Column("classe", sa.String(length=20), server_default="aberta", nullable=False),
        sa.Column("vezes_usada", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usada_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # (chave, escopo, empresa) e não só chave: pergunta aberta tem uma
        # resposta por empresa, e sem a empresa a segunda sobrescreveria a
        # primeira em silêncio.
        sa.UniqueConstraint("chave", "escopo", "empresa",
                            name="uq_respostas_chave_escopo_empresa"),
    )
    op.create_index("ix_respostas_aprendidas_chave", "respostas_aprendidas", ["chave"])


def downgrade() -> None:
    op.drop_index("ix_respostas_aprendidas_chave", table_name="respostas_aprendidas")
    op.drop_table("respostas_aprendidas")
