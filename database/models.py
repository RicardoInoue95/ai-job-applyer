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
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
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
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CacheGemini(Base):
    __tablename__ = "cache_gemini"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chave_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    modelo: Mapped[str] = mapped_column(String(100))
    resposta: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expira_em: Mapped[datetime] = mapped_column(DateTime, index=True)
