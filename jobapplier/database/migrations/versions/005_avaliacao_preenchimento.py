"""avaliação de preenchimento: a evidência que o modo sombra não coletava

Revision ID: 005
Revises: 004
Create Date: 2026-08-17

O modo sombra respondia "eu teria me candidatado?" e não respondia "eu
conseguiria preencher?" — porque pulava o applicator inteiro e portanto nunca
descobria quais campos o formulário tem.

São perguntas diferentes: uma vaga pode ter aderência excelente e um formulário
que a automação não sabe completar. Sem esta coluna, rodar o modo sombra por
semanas não produziria a taxa de formulários desconhecidos, que é justamente um
dos critérios para desligá-lo.

Guarda o resultado de `applicators.base.avaliar_preenchimento`: método usado,
campos respondidos, desconhecidos, bloqueadores e a confiança resultante.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidaturas",
        sa.Column("avaliacao_preenchimento_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidaturas", "avaliacao_preenchimento_json")
