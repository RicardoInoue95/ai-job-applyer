from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from jobapplier.tempo import agora_utc


class Base(DeclarativeBase):
    pass


class Vaga(Base):
    __tablename__ = "vagas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    titulo: Mapped[str] = mapped_column(String(500))
    empresa: Mapped[str] = mapped_column(String(200))
    plataforma: Mapped[str] = mapped_column(String(50))
    localizacao: Mapped[str | None] = mapped_column(Text)
    modalidade: Mapped[str | None] = mapped_column(String(50))
    senioridade: Mapped[str | None] = mapped_column(String(50))
    salario: Mapped[str | None] = mapped_column(String(100))
    descricao: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(1000))
    data_publicacao: Mapped[datetime | None] = mapped_column(DateTime)
    normalizado_json: Mapped[dict | None] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Float)
    score_breakdown_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="nova")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)


class Candidatura(Base):
    __tablename__ = "candidaturas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vaga_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pendente")
    perfil_base: Mapped[str | None] = mapped_column(String(50))
    curriculo_path: Mapped[str | None] = mapped_column(String(500))
    ats_score_original: Mapped[float | None] = mapped_column(Float)
    ats_score_otimizado: Mapped[float | None] = mapped_column(Float)
    keywords_adicionadas: Mapped[list | None] = mapped_column(JSON)
    cover_letter_path: Mapped[str | None] = mapped_column(String(500))
    screenshots_path: Mapped[str | None] = mapped_column(String(500))
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=agora_utc, onupdate=agora_utc
    )


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    segmento: Mapped[str | None] = mapped_column(String(100))
    tamanho: Mapped[str | None] = mapped_column(String(50))
    tecnologias: Mapped[list | None] = mapped_column(JSON)
    sobre: Mapped[str | None] = mapped_column(Text)
    noticias: Mapped[list | None] = mapped_column(JSON)
    resumo: Mapped[str | None] = mapped_column(Text)
    pesquisado_em: Mapped[datetime | None] = mapped_column(DateTime)


class AprovacoesHistorico(Base):
    __tablename__ = "aprovacoes_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vaga_id: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float] = mapped_column(Float)
    aprovado: Mapped[bool] = mapped_column(Boolean)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)


class Execucao(Base):
    """Uma execução de esteira do pipeline: coleta, pipeline ou candidaturas.

    Serve a dois propósitos de propósito. Hoje é observabilidade durável — a
    única forma de responder "o que rodou ontem e o que falhou" depois que o
    terminal fechou. Amanhã, no desenho multi-usuário, é a linha de fila: ganha
    `usuario_id` e um worker consome as pendentes.
    """

    __tablename__ = "execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    tipo: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="em_andamento", index=True)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc, index=True)
    terminado_em: Mapped[datetime | None] = mapped_column(DateTime)
    metricas_json: Mapped[dict | None] = mapped_column(JSON)
    erro: Mapped[str | None] = mapped_column(Text)


class CacheGemini(Base):
    __tablename__ = "cache_gemini"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chave_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    modelo: Mapped[str] = mapped_column(String(100))
    resposta: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
    expira_em: Mapped[datetime] = mapped_column(DateTime, index=True)
