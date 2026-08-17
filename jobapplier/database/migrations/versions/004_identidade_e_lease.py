"""identidade estável da vaga, idempotência no banco e lease de processamento

Revision ID: 004
Revises: 003
Create Date: 2026-08-17

Três problemas resolvidos aqui.

1. IDENTIDADE. A dedup era sha256(titulo + empresa + link). Quebrava quando o
   link ganhava parâmetro, a vaga era republicada ou o título mudava um caractere
   — a mesma vaga entrava de novo. As três APIs devolvem um id próprio e o
   projeto descartava: o Greenhouse ignorava `item["id"]` e depois o applicator o
   recuperava por regex do `absolute_url`.

   `hash` continua unique e não muda de fórmula, senão toda linha existente
   pareceria nova. O índice novo é PARCIAL (só onde fonte_vaga_id não é nulo),
   então linhas antigas seguem válidas.

2. IDEMPOTÊNCIA. Não havia constraint alguma em candidaturas: a proteção contra
   duplicata era só `guard.ja_candidatado()`, em código. Para uma ação
   irreversível como enviar candidatura, a garantia tem de estar no banco.
   `ciclo` torna recandidatura explícita em vez de simplesmente proibida.

3. LEASE. `liberar_orfaos()` devolvia TODA vaga em 'em_andamento' para a fila,
   correto apenas sob a suposição de que max_instances=1. Com lease, órfão é o
   que tem lease expirado — o que continua correto se houver concorrência.
   `tentativas` impede que uma vaga que envenena o processo volte para sempre.

A migration é aditiva: nenhuma coluna existente muda de tipo e nenhum dado é
reescrito. O backfill de fonte_vaga_id para linhas antigas NÃO é feito aqui — o
id teria de ser reextraído do link por plataforma, e é melhor fazer isso num
script separado, verificável, do que dentro de uma migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── vagas: identidade ────────────────────────────────────────────────────
    op.add_column("vagas", sa.Column("fonte_vaga_id", sa.String(120), nullable=True))
    op.add_column("vagas", sa.Column("fonte_empresa_id", sa.String(120), nullable=True))
    op.add_column("vagas", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index("ix_vagas_fonte_vaga_id", "vagas", ["fonte_vaga_id"])
    op.create_index("ix_vagas_fonte_empresa_id", "vagas", ["fonte_empresa_id"])
    op.create_index(
        "uq_vagas_plataforma_fonte_id",
        "vagas",
        ["plataforma", "fonte_vaga_id"],
        unique=True,
        postgresql_where=sa.text("fonte_vaga_id IS NOT NULL"),
    )

    # ── vagas: ciclo de vida ─────────────────────────────────────────────────
    op.add_column("vagas", sa.Column("primeira_coleta_em", sa.DateTime(), nullable=True))
    op.add_column("vagas", sa.Column("ultima_coleta_em", sa.DateTime(), nullable=True))
    op.add_column("vagas", sa.Column("encerrada_em", sa.DateTime(), nullable=True))
    op.create_index("ix_vagas_ultima_coleta_em", "vagas", ["ultima_coleta_em"])

    # Linhas existentes não têm histórico de coleta; criado_em é a melhor
    # aproximação disponível para a primeira vez que a vaga foi vista.
    op.execute(
        "UPDATE vagas SET primeira_coleta_em = criado_em, ultima_coleta_em = criado_em "
        "WHERE primeira_coleta_em IS NULL"
    )

    # ── vagas: lease ─────────────────────────────────────────────────────────
    op.add_column("vagas", sa.Column("bloqueado_em", sa.DateTime(), nullable=True))
    op.add_column("vagas", sa.Column("bloqueado_por", sa.String(64), nullable=True))
    op.add_column("vagas", sa.Column("lease_expira_em", sa.DateTime(), nullable=True))
    op.add_column(
        "vagas",
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_vagas_lease_expira_em", "vagas", ["lease_expira_em"])

    # ── candidaturas: idempotência ───────────────────────────────────────────
    op.add_column(
        "candidaturas",
        sa.Column("ciclo", sa.Integer(), nullable=False, server_default="1"),
    )

    # Linhas duplicadas pré-existentes impediriam criar a constraint. Em vez de
    # falhar a migration ou apagar histórico, cada duplicata recebe um ciclo
    # próprio, preservando o dado e permitindo a constraint.
    op.execute(
        """
        WITH numeradas AS (
            SELECT id, ROW_NUMBER() OVER (
                       PARTITION BY vaga_id ORDER BY criado_em, id
                   ) AS n
            FROM candidaturas
        )
        UPDATE candidaturas c
           SET ciclo = numeradas.n
          FROM numeradas
         WHERE c.id = numeradas.id
        """
    )
    op.create_unique_constraint(
        "uq_candidaturas_vaga_ciclo", "candidaturas", ["vaga_id", "ciclo"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_candidaturas_vaga_ciclo", "candidaturas", type_="unique")
    op.drop_column("candidaturas", "ciclo")

    op.drop_index("ix_vagas_lease_expira_em", table_name="vagas")
    op.drop_column("vagas", "tentativas")
    op.drop_column("vagas", "lease_expira_em")
    op.drop_column("vagas", "bloqueado_por")
    op.drop_column("vagas", "bloqueado_em")

    op.drop_index("ix_vagas_ultima_coleta_em", table_name="vagas")
    op.drop_column("vagas", "encerrada_em")
    op.drop_column("vagas", "ultima_coleta_em")
    op.drop_column("vagas", "primeira_coleta_em")

    op.drop_index("uq_vagas_plataforma_fonte_id", table_name="vagas")
    op.drop_index("ix_vagas_fonte_empresa_id", table_name="vagas")
    op.drop_index("ix_vagas_fonte_vaga_id", table_name="vagas")
    op.drop_column("vagas", "content_hash")
    op.drop_column("vagas", "fonte_empresa_id")
    op.drop_column("vagas", "fonte_vaga_id")
