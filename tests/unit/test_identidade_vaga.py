"""Resolução da identidade de uma vaga do Greenhouse.

O parser antigo falhava em 26% do acervo real. Duas causas independentes:
tomava o subdomínio pelo domínio (`careers.airbnb.com` → `careers`) e dependia
de um mapa fixo que não acompanha a cauda longa de empresas.

A matriz abaixo cobre os formatos de URL que aparecem na prática, mais os casos
degenerados que um parser precisa recusar sem estourar.
"""
import types

import pytest

from jobapplier.applicators.identidade import IdentidadeVaga, resolver


def vaga(link="", empresa=None, fonte_vaga_id=None, fonte_empresa_id=None):
    return types.SimpleNamespace(
        link=link, empresa=empresa,
        fonte_vaga_id=fonte_vaga_id, fonte_empresa_id=fonte_empresa_id,
    )


# ── Prioridade: o registro vence a URL ────────────────────────────────────────

def test_identidade_do_registro_tem_precedencia():
    """O coletor já guardou slug e id. Re-derivar da URL era descartar dado."""
    r = resolver(vaga(
        link="https://qualquer.coisa/errado",
        fonte_vaga_id="4012345", fonte_empresa_id="nubank",
    ))
    assert (r.slug, r.job_id, r.origem) == ("nubank", "4012345", "registro")
    assert r.confiavel


def test_empresa_serve_de_slug_quando_nao_ha_fonte_empresa_id():
    """Vagas antigas não têm fonte_empresa_id, mas `empresa` guarda o slug."""
    r = resolver(vaga(link="https://x/y", empresa="stone", fonte_vaga_id="777"))
    assert (r.slug, r.origem) == ("stone", "registro")


def test_registro_com_slug_invalido_cai_para_a_url():
    """Nome de empresa com espaço não é slug de board."""
    r = resolver(vaga(
        link="https://boards.greenhouse.io/acme/jobs/999",
        empresa="Acme Corporation", fonte_vaga_id="123",
    ))
    assert (r.slug, r.job_id, r.origem) == ("acme", "999", "url_canonica")


# ── URL canônica do board ─────────────────────────────────────────────────────

@pytest.mark.parametrize("url,slug,job_id", [
    ("https://boards.greenhouse.io/nubank/jobs/4012345", "nubank", "4012345"),
    ("https://job-boards.greenhouse.io/stone/jobs/555", "stone", "555"),
    ("https://job-boards.eu.greenhouse.io/getnet/jobs/4901923101", "getnet", "4901923101"),
    ("https://boards.greenhouse.io/acme/jobs/1?utm=x", "acme", "1"),
    ("https://boards.greenhouse.io/acme/jobs/1#apply", "acme", "1"),
])
def test_url_canonica(url, slug, job_id):
    r = resolver(link=url)
    assert (r.slug, r.job_id, r.origem) == (slug, job_id, "url_canonica")
    assert r.confiavel


# ── gh_jid no domínio da empresa ──────────────────────────────────────────────

@pytest.mark.parametrize("url,slug", [
    # O bug: estes viravam "careers"/"jobs" porque o código pegava o 1º rótulo.
    ("https://careers.airbnb.com/positions/7454348?gh_jid=7454348", "airbnb"),
    ("https://careers.datadoghq.com/detail/7696093/?gh_jid=7696093", "datadog"),
    ("https://jobs.elastic.co/jobs/x?gh_jid=123", "elastic"),
    ("https://careers.duolingo.com/positions?gh_jid=456", "duolingo"),
    # Domínio simples.
    ("https://sumup.com/careers/x?gh_jid=789", "sumup"),
    ("https://databricks.com/company/careers/open-positions/job?gh_jid=5507088002",
     "databricks"),
    ("https://stripe.com/jobs/search?gh_jid=6543", "stripe"),
    ("https://www.thoughtworks.com/careers/jobs/x?gh_jid=111", "thoughtworks"),
    ("https://www.mongodb.com/careers/x?gh_jid=222", "mongodb"),
    ("https://www.asana.com/jobs/x?gh_jid=333", "asana"),
])
def test_gh_jid_no_dominio_da_empresa(url, slug):
    r = resolver(link=url)
    assert r is not None, url
    assert r.slug == slug
    assert r.origem == "dominio"
    # Slug derivado de domínio é palpite: exige confirmação pela API.
    assert not r.confiavel


@pytest.mark.parametrize("url", [
    "https://acme.com/jobs?gh_jid=42&utm_source=x",          # parâmetro extra
    "https://acme.com/jobs?utm_source=x&gh_jid=42",          # ordem diferente
    "https://acme.com/jobs?gh_jid=42#apply",                 # fragmento
    "https://acme.com/jobs/?gh_jid=42",                      # barra final
    "https://acme.com/jobs?gh_jid=99&gh_jid=42",             # repetido
])
def test_variacoes_de_query_string(url):
    r = resolver(link=url)
    assert r is not None, url
    assert r.slug == "acme"
    assert r.job_id in ("42", "99")


def test_dominio_composto_brasileiro():
    assert resolver(link="https://vagas.empresa.com.br/x?gh_jid=1").slug == "empresa"


# ── Casos que devem ser recusados, sem estourar ───────────────────────────────

@pytest.mark.parametrize("url", [
    "",
    "não é uma url",
    "https://acme.com/jobs",                    # sem gh_jid
    "https://acme.com/jobs?gh_jid=",            # gh_jid vazio
    "https://acme.com/jobs?gh_jid=abc",         # gh_jid não numérico
    "https://acme.com/jobs?ghjid=42",           # parâmetro parecido
    "https://boards.greenhouse.io/acme/jobs/",  # sem id
    "ftp://acme.com?gh_jid=1",                  # esquema estranho, sem host útil
])
def test_url_sem_identidade_devolve_none(url):
    assert resolver(link=url) is None


def test_sem_vaga_e_sem_link():
    assert resolver() is None


def test_vaga_sem_nenhum_campo_util():
    assert resolver(vaga()) is None


# ── Propriedades da identidade ────────────────────────────────────────────────

def test_url_canonica_reconstruida():
    r = IdentidadeVaga("nubank", "4012345", "registro")
    assert r.url_canonica == "https://boards.greenhouse.io/nubank/jobs/4012345"


def test_confiabilidade_por_origem():
    assert IdentidadeVaga("a", "1", "registro").confiavel
    assert IdentidadeVaga("a", "1", "url_canonica").confiavel
    # Palpite sobre o domínio nunca é confiável sem confirmar na API.
    assert not IdentidadeVaga("a", "1", "dominio").confiavel


def test_gh_jid_nao_transforma_qualquer_dominio_em_greenhouse():
    """Detectar gh_jid dá um palpite de slug, não uma certeza de plataforma."""
    r = resolver(link="https://site-aleatorio.example/vaga?gh_jid=1")
    assert r is not None
    assert not r.confiavel, "slug derivado de domínio precisa ser confirmado"
