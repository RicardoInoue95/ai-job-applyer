"""tabela execucoes: observabilidade durável e futura fila

Revision ID: 003
Revises: 002
Create Date: 2026-08-17

Antes desta tabela, a única evidência de uma execução era o stdout do processo.
Com o orquestrador rodando a cada 2h sem supervisão, uma falha noturna não
deixava rastro consultável.

O índice composto (tipo, iniciado_em) serve à pergunta que se faz na prática:
"as últimas execuções de candidatura, da mais recente para a mais antiga".
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execucoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="em_andamento"),
        sa.Column("iniciado_em", sa.DateTime(), nullable=False),
        sa.Column("terminado_em", sa.DateTime(), nullable=True),
        sa.Column("metricas_json", sa.JSON(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
    )
    op.create_index("ix_execucoes_run_id", "execucoes", ["run_id"])
    op.create_index("ix_execucoes_tipo", "execucoes", ["tipo"])
    op.create_index("ix_execucoes_status", "execucoes", ["status"])
    op.create_index("ix_execucoes_iniciado_em", "execucoes", ["iniciado_em"])
    op.create_index("ix_execucoes_tipo_iniciado", "execucoes", ["tipo", "iniciado_em"])


def downgrade() -> None:
    op.drop_index("ix_execucoes_tipo_iniciado", table_name="execucoes")
    op.drop_index("ix_execucoes_iniciado_em", table_name="execucoes")
    op.drop_index("ix_execucoes_status", table_name="execucoes")
    op.drop_index("ix_execucoes_tipo", table_name="execucoes")
    op.drop_index("ix_execucoes_run_id", table_name="execucoes")
    op.drop_table("execucoes")
