"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vagas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("plataforma", sa.String(50), nullable=False),
        sa.Column("localizacao", sa.String(200), nullable=True),
        sa.Column("modalidade", sa.String(50), nullable=True),
        sa.Column("senioridade", sa.String(50), nullable=True),
        sa.Column("salario", sa.String(100), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.String(1000), nullable=False),
        sa.Column("data_publicacao", sa.DateTime(), nullable=True),
        sa.Column("normalizado_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_breakdown_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="nova"),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hash"),
    )
    op.create_index("ix_vagas_hash", "vagas", ["hash"])
    op.create_index("ix_vagas_status", "vagas", ["status"])

    op.create_table(
        "candidaturas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vaga_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pendente"),
        sa.Column("perfil_base", sa.String(50), nullable=True),
        sa.Column("curriculo_path", sa.String(500), nullable=True),
        sa.Column("ats_score_original", sa.Float(), nullable=True),
        sa.Column("ats_score_otimizado", sa.Float(), nullable=True),
        sa.Column("keywords_adicionadas", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("cover_letter_path", sa.String(500), nullable=True),
        sa.Column("screenshots_path", sa.String(500), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidaturas_vaga_id", "candidaturas", ["vaga_id"])

    op.create_table(
        "empresas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("segmento", sa.String(100), nullable=True),
        sa.Column("tamanho", sa.String(50), nullable=True),
        sa.Column("tecnologias", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("sobre", sa.Text(), nullable=True),
        sa.Column("noticias", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("pesquisado_em", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
    )
    op.create_index("ix_empresas_nome", "empresas", ["nome"])

    op.create_table(
        "aprovacoes_historico",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vaga_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("aprovado", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aprovacoes_vaga_id", "aprovacoes_historico", ["vaga_id"])

    op.create_table(
        "cache_gemini",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chave_hash", sa.String(64), nullable=False),
        sa.Column("modelo", sa.String(100), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chave_hash"),
    )
    op.create_index("ix_cache_gemini_chave_hash", "cache_gemini", ["chave_hash"])
    op.create_index("ix_cache_gemini_expira_em", "cache_gemini", ["expira_em"])


def downgrade() -> None:
    op.drop_table("cache_gemini")
    op.drop_table("aprovacoes_historico")
    op.drop_table("empresas")
    op.drop_table("candidaturas")
    op.drop_table("vagas")
