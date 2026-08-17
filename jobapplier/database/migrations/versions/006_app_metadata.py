"""app_metadata: identidade explícita da aplicação dona do banco

Revision ID: 006
Revises: 005
Create Date: 2026-08-17

A confirmação de identidade hoje usa nome do banco e nomes de tabela. Os dois
são frágeis: nome pode coincidir, tabela pode ser renomeada, e um banco vazio
chamado 'jobapplier' passaria.

Esta tabela é o terceiro sinal, e o único que a aplicação escreve
deliberadamente. Com ela, a confirmação passa a ter três provas independentes:

    nome do banco  +  marcador da aplicação  +  revisão do Alembic

Nasceu de um quase-acidente real: outro projeto ocupava a porta 5432 e o
DATABASE_URL apontava para lá. Um upgrade teria migrado base alheia; só a senha
não bater impediu.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPLICATION_ID = "ai_job_applier"


def upgrade() -> None:
    op.create_table(
        "app_metadata",
        sa.Column("chave", sa.String(64), primary_key=True),
        sa.Column("valor", sa.Text(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
    )
    op.execute(
        "INSERT INTO app_metadata (chave, valor, atualizado_em) VALUES "
        f"('application_id', '{APPLICATION_ID}', NOW()), "
        "('schema_generation', '1', NOW())"
    )


def downgrade() -> None:
    op.drop_table("app_metadata")
