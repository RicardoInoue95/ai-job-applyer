"""
Testes de integração — requerem PostgreSQL rodando.
Execute com: pytest -m db

Para subir o banco: docker compose up postgres -d

Sem Postgres disponível, cada teste é pulado com motivo explícito em vez de
falhar — mas continue tratando um skip como cobertura ausente, não como sucesso.
"""
import hashlib
from datetime import datetime

import pytest

from database.connection import DATABASE_URL, get_session
from database.models import Vaga
from database.repository import VagaRepository

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def db_available():
    from sqlalchemy import create_engine, text
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def make_vaga(title="Data Engineer", company="test-co", link=None) -> Vaga:
    link = link or f"https://example.com/jobs/{title.lower().replace(' ', '-')}"
    hash_ = hashlib.sha256(f"{title}{company}{link}".encode()).hexdigest()
    return Vaga(
        hash=hash_,
        titulo=title,
        empresa=company,
        plataforma="greenhouse",
        localizacao="Remote",
        descricao="Test job description",
        link=link,
        criado_em=datetime.utcnow(),
    )


def test_insert_and_deduplication(db_available):
    if not db_available:
        pytest.skip("PostgreSQL não disponível")

    vaga1 = make_vaga("Test Engineer", "test-company-dedup")
    vaga2 = make_vaga("Test Engineer", "test-company-dedup")

    with get_session() as session:
        repo = VagaRepository(session)
        # Limpar dados de testes anteriores
        session.query(Vaga).filter(Vaga.empresa == "test-company-dedup").delete()

        inserted1, skipped1 = repo.bulk_create_if_not_exists([vaga1])
        assert inserted1 == 1
        assert skipped1 == 0

        inserted2, skipped2 = repo.bulk_create_if_not_exists([vaga2])
        assert inserted2 == 0
        assert skipped2 == 1

        count = session.query(Vaga).filter(Vaga.empresa == "test-company-dedup").count()
        assert count == 1

        # Cleanup
        session.query(Vaga).filter(Vaga.empresa == "test-company-dedup").delete()


def test_exists_by_hash(db_available):
    if not db_available:
        pytest.skip("PostgreSQL não disponível")

    vaga = make_vaga("Hash Test", "test-company-hash")

    with get_session() as session:
        session.query(Vaga).filter(Vaga.empresa == "test-company-hash").delete()
        repo = VagaRepository(session)

        assert not repo.exists_by_hash(vaga.hash)
        repo.create(vaga)
        assert repo.exists_by_hash(vaga.hash)

        session.query(Vaga).filter(Vaga.empresa == "test-company-hash").delete()


def test_list_novas(db_available):
    if not db_available:
        pytest.skip("PostgreSQL não disponível")

    with get_session() as session:
        session.query(Vaga).filter(Vaga.empresa == "test-company-novas").delete()

        repo = VagaRepository(session)
        v1 = make_vaga("Job A", "test-company-novas", "https://a.com")
        v2 = make_vaga("Job B", "test-company-novas", "https://b.com")
        repo.bulk_create_if_not_exists([v1, v2])

        novas = repo.list_novas()
        empresa_novas = [v for v in novas if v.empresa == "test-company-novas"]
        assert len(empresa_novas) == 2

        session.query(Vaga).filter(Vaga.empresa == "test-company-novas").delete()
