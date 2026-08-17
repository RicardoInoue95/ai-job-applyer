import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobapplier.config import secrets

# Carrega .env antes de resolver a URL do banco.
secrets.carregar_env()

# DATABASE_URL (sem prefixo) é mantido por compatibilidade: run.py o injeta no
# ambiente dos subprocessos. AIJOB_DATABASE_URL, via secrets, tem precedência.
DATABASE_URL = secrets.obter("DATABASE_URL", "database_url") or os.environ.get(
    "DATABASE_URL",
    "postgresql://jobapplier:jobapplier@localhost:55432/jobapplier",
)

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session() -> Session:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
