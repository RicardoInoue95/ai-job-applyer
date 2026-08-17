"""Identidade da vaga e integridade do schema.

A dedup era sha256(titulo + empresa + link): quebrava com parâmetro extra no
link, republicação ou mudança de título, e a mesma vaga entrava de novo. As três
APIs devolvem um id próprio e o projeto descartava — o Greenhouse ignorava
`item["id"]` e o applicator depois o recuperava por regex do `absolute_url`.
"""
import re
from pathlib import Path

from jobapplier.collectors.base import CollectedJob
from jobapplier.database.models import Candidatura, Vaga

MIGRATIONS = Path(__file__).resolve().parents[2] / "jobapplier/database/migrations/versions"


def vaga(**kw) -> CollectedJob:
    base = {
        "titulo": "Data Engineer",
        "empresa": "nubank",
        "plataforma": "greenhouse",
        "link": "https://boards.greenhouse.io/nubank/jobs/4012345",
        "descricao": "Descrição da vaga.",
    }
    return CollectedJob(**{**base, **kw})


# ── Identidade estável ────────────────────────────────────────────────────────

def test_identidade_sobrevive_parametro_no_link():
    a = vaga(link="https://x/jobs/1?gh_src=abc", fonte_vaga_id="4012345")
    b = vaga(link="https://x/jobs/1?gh_src=xyz&utm=1", fonte_vaga_id="4012345")
    assert a.hash != b.hash, "o hash legado muda — era a origem do problema"
    assert a.identidade == b.identidade


def test_identidade_sobrevive_mudanca_de_titulo():
    a = vaga(titulo="Data Engineer", fonte_vaga_id="4012345")
    b = vaga(titulo="Data Engineer (Sênior)", fonte_vaga_id="4012345")
    assert a.hash != b.hash
    assert a.identidade == b.identidade


def test_identidade_distingue_vagas_diferentes():
    assert vaga(fonte_vaga_id="1").identidade != vaga(fonte_vaga_id="2").identidade


def test_identidade_inclui_plataforma():
    """Ids de plataformas diferentes podem colidir numericamente."""
    a = vaga(plataforma="greenhouse", fonte_vaga_id="123")
    b = vaga(plataforma="gupy", fonte_vaga_id="123")
    assert a.identidade != b.identidade


def test_id_numerico_e_normalizado_para_str():
    assert vaga(fonte_vaga_id=4012345).fonte_vaga_id == "4012345"


def test_id_vazio_ou_espacos_vira_none():
    assert vaga(fonte_vaga_id="").fonte_vaga_id is None
    assert vaga(fonte_vaga_id="   ").fonte_vaga_id is None
    assert vaga(fonte_vaga_id="  ").identidade is None


def test_sem_id_nao_tem_identidade():
    assert vaga().identidade is None


def test_hash_legado_nao_mudou_de_formula():
    """Mudar a fórmula faria toda linha do banco parecer nova."""
    import hashlib

    j = vaga()
    esperado = hashlib.sha256(f"{j.titulo}{j.empresa}{j.link}".encode()).hexdigest()
    assert j.hash == esperado


# ── content_hash ──────────────────────────────────────────────────────────────

def test_content_hash_muda_com_a_descricao():
    assert vaga(descricao="a").content_hash != vaga(descricao="b").content_hash


def test_content_hash_ignora_titulo_e_link():
    a = vaga(titulo="X", link="l1", descricao="mesma")
    b = vaga(titulo="Y", link="l2", descricao="mesma")
    assert a.content_hash == b.content_hash


def test_content_hash_e_estavel():
    assert vaga(descricao="d").content_hash == vaga(descricao="d").content_hash


def test_descricao_vazia_ainda_gera_content_hash():
    assert len(vaga(descricao="").content_hash) == 64


# ── Schema: models x migration ────────────────────────────────────────────────

def _sql_das_migrations() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("0*.py"))
    )


def test_toda_coluna_de_vaga_existe_em_alguma_migration():
    """Drift entre models e migrations gera erro só em runtime, no banco novo."""
    sql = _sql_das_migrations()
    faltando = [c.name for c in Vaga.__table__.columns if f'"{c.name}"' not in sql]
    assert not faltando, f"colunas de vagas ausentes nas migrations: {faltando}"


def test_toda_coluna_de_candidatura_existe_em_alguma_migration():
    sql = _sql_das_migrations()
    faltando = [c.name for c in Candidatura.__table__.columns if f'"{c.name}"' not in sql]
    assert not faltando, f"colunas de candidaturas ausentes: {faltando}"


def test_constraint_de_idempotencia_existe_nos_models_e_na_migration():
    nomes = {c.name for c in Candidatura.__table__.constraints if c.name}
    assert "uq_candidaturas_vaga_ciclo" in nomes
    assert "uq_candidaturas_vaga_ciclo" in _sql_das_migrations()


def test_indice_unico_de_identidade_e_parcial():
    """Parcial porque linhas antigas têm fonte_vaga_id nulo e são válidas."""
    idx = next(
        i for i in Vaga.__table__.indexes if i.name == "uq_vagas_plataforma_fonte_id"
    )
    assert idx.unique
    assert idx.dialect_options["postgresql"]["where"] is not None
    assert {c.name for c in idx.columns} == {"plataforma", "fonte_vaga_id"}


def test_migrations_formam_cadeia_sem_furo():
    revisoes, anteriores = {}, {}
    for p in sorted(MIGRATIONS.glob("0*.py")):
        texto = p.read_text(encoding="utf-8")
        rev = re.search(r'^revision: str = "(\w+)"', texto, re.M).group(1)
        down = re.search(r'^down_revision: [^=]+= (?:"(\w+)"|None)', texto, re.M).group(1)
        revisoes[rev] = p.name
        anteriores[rev] = down

    assert len(revisoes) >= 4
    # Exatamente uma raiz.
    assert sum(1 for d in anteriores.values() if d is None) == 1
    # Todo down_revision aponta para revisão existente.
    for rev, down in anteriores.items():
        if down is not None:
            assert down in revisoes, f"{rev} referencia revisão inexistente {down}"
    # Nenhuma revisão é pai de duas (sem ramificação).
    pais = [d for d in anteriores.values() if d is not None]
    assert len(pais) == len(set(pais)), "há ramificação nas migrations"


def test_toda_migration_tem_downgrade():
    for p in sorted(MIGRATIONS.glob("0*.py")):
        texto = p.read_text(encoding="utf-8")
        assert "def downgrade()" in texto, f"{p.name} sem downgrade"
        corpo = texto.split("def downgrade()")[1]
        assert corpo.strip() not in ("", "-> None:\n    pass"), f"{p.name}: downgrade vazio"


# ── Lease ─────────────────────────────────────────────────────────────────────

def test_lease_tem_duracao_e_teto_de_tentativas():
    from jobapplier.safety import guard

    assert guard.LEASE_MINUTOS > 0
    assert guard.MAX_TENTATIVAS_VAGA >= 1


def test_colunas_de_lease_existem():
    for coluna in ("bloqueado_em", "bloqueado_por", "lease_expira_em", "tentativas"):
        assert coluna in Vaga.__table__.columns, coluna
