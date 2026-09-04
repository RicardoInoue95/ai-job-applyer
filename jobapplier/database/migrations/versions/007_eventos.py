"""eventos: o desfecho depois de candidatar

O funil morria em 'candidatada'. Sem esta tabela, o limiar de score nunca pôde
ser validado contra realidade — só contra métrica interna.

Revision ID: 007
Revises: 006
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eventos",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("vaga_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("fonte", sa.String(length=20), nullable=False,
                  server_default="email"),
        sa.Column("referencia", sa.String(length=300), nullable=True),
        sa.Column("ocorrido_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        # A empresa reenvia o mesmo aviso; contar duplicata inflaria justamente
        # o número que esta tabela existe para tornar confiável.
        sa.UniqueConstraint("vaga_id", "tipo", name="uq_eventos_vaga_tipo"),
    )
    op.create_index("ix_eventos_vaga_id", "eventos", ["vaga_id"])
    op.create_index("ix_eventos_tipo", "eventos", ["tipo"])


def downgrade() -> None:
    op.drop_index("ix_eventos_tipo", table_name="eventos")
    op.drop_index("ix_eventos_vaga_id", table_name="eventos")
    op.drop_table("eventos")
