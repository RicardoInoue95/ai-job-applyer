"""Slug de board não é nome de empresa.

A carta de apresentação abria com "Prezada equipe de c6bank" — 74 das 299 cartas
já geradas traziam o slug cru. É o texto que o recrutador lê, e slug em minúsculo
lê como formulário automático, que é a impressão que a carta existe para evitar.
"""
import pytest

from jobapplier import empresas
from jobapplier.empresas import nome_exibicao


@pytest.mark.parametrize("slug,esperado", [
    ("c6bank", "C6 Bank"),
    ("quintoandar", "QuintoAndar"),
    ("gitlab", "GitLab"),
    ("jfrog", "JFrog"),
    ("vtex", "VTEX"),
    ("ifood", "iFood"),
])
def test_excecoes_conhecidas(slug, esperado):
    assert nome_exibicao(slug) == esperado


@pytest.mark.parametrize("slug,esperado", [
    ("twilio", "Twilio"),
    ("airbnb", "Airbnb"),
    ("affirm", "Affirm"),
    ("datadog", "Datadog"),
    ("intercom", "Intercom"),
])
def test_titulo_simples_resolve_a_maioria(slug, esperado):
    """Um mapa das 157 empresas seria mais uma cópia para divergir do
    config.json. O mapa só carrega o que o título erra."""
    assert nome_exibicao(slug) == esperado


@pytest.mark.parametrize("slug,esperado", [
    ("acme-tech", "Acme Tech"),
    ("acme_tech", "Acme Tech"),
    ("grupo-boticario", "Grupo Boticario"),
])
def test_separador_vira_espaco(slug, esperado):
    assert nome_exibicao(slug) == esperado


@pytest.mark.parametrize("nome", ["C6 Bank", "Stefanini Group", "iFood", "XP Inc"])
def test_nome_ja_escrito_por_humano_passa_intacto(nome):
    """Gupy e inhire devolvem nome de verdade, não slug. Reprocessar estragaria
    "iFood" e "XP Inc" — `.title()` não sabe que a caixa era intencional."""
    assert nome_exibicao(nome) == nome


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_vazio_devolve_vazio_e_nao_um_fallback(vazio):
    """Quem chama escolhe o texto de ausência: a carta usa "a empresa". Um
    fallback aqui esconderia a ausência de quem precisa tratá-la."""
    assert nome_exibicao(vazio) == ""


def test_excecao_nao_repete_o_que_o_titulo_ja_acerta():
    """Entrada redundante envelhece sem ninguém perceber."""
    redundantes = [s for s, nome in empresas.EXCECOES.items() if s.title() == nome]
    assert not redundantes, f"{redundantes} já saem certas por .title()"


# ── Contrato com a carta ──────────────────────────────────────────────────────

def test_carta_nao_abre_com_slug_cru():
    from types import SimpleNamespace

    from jobapplier.agents.cover_letter import generate

    vaga = SimpleNamespace(
        empresa="c6bank", titulo="Analista de Dados Pleno",
        normalizado_json={"cargo": "Analista de Dados Pleno",
                          "tecnologias": ["Python", "SQL"]})
    resume = {"nome": "Ricardo Y. K. Inoue", "tecnologias": ["Python", "SQL"],
              "experiencias": [{"cargo": "Coordenador de Dados", "conquistas": []}]}

    texto = generate(resume, vaga, None)
    assert "C6 Bank" in texto
    assert "c6bank" not in texto


# ── Idioma da carta ───────────────────────────────────────────────────────────
# A carta saía sempre em português, inclusive junto de currículo em inglês —
# metade da fila, no mesmo envelope. O idioma vem do currículo recebido, não da
# vaga: quem escolheu o mestre pt ou en foi `perfis.montar`, e a carta acompanha
# o documento que vai com ela.

def _vaga_en():
    from types import SimpleNamespace

    return SimpleNamespace(
        empresa="adyen", titulo="Payments Performance Analyst",
        normalizado_json={"cargo": "Payments Performance Analyst",
                          "tecnologias": ["Python", "SQL"]})


def test_carta_acompanha_curriculo_em_ingles():
    from jobapplier import idioma
    from jobapplier.agents.cover_letter import generate
    from jobapplier.perfis import montar

    texto = generate(montar("data_engineer", "en"), _vaga_en(), None)
    assert idioma.detectar(texto) == "en"
    assert "Dear Adyen team" in texto
    assert "Prezada" not in texto


@pytest.mark.pessoal
def test_carta_acompanha_curriculo_em_portugues():
    from jobapplier import idioma
    from jobapplier.agents.cover_letter import generate
    from jobapplier.perfis import montar

    texto = generate(montar("data_engineer", "pt"), _vaga_en(), None)
    assert idioma.detectar(texto) == "pt"
    assert "Prezada equipe de Adyen" in texto


def test_dossie_passa_o_curriculo_escolhido_para_a_carta():
    """Contrato: `dossie.montar` passava o mestre bruto, e por isso o idioma da
    carta ignorava a escolha feita para o currículo."""
    import inspect

    from jobapplier import dossie

    fonte = inspect.getsource(dossie.montar)
    assert "gerar_carta(base" in fonte
    assert "gerar_carta(resume_json" not in fonte


def test_toda_frase_existe_nos_dois_idiomas():
    """Acrescentar idioma tem de ser acrescentar uma chave, não caçar f-string."""
    from jobapplier.agents.cover_letter import _FRASES

    assert set(_FRASES["pt"]) == set(_FRASES["en"])
