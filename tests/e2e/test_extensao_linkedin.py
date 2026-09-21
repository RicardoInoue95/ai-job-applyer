"""Leitura do perfil do LinkedIn pela extensão, contra uma página sintética.

A fixture reproduz a estrutura conhecida do perfil — âncoras por seção, itens
de lista, texto duplicado em `span[aria-hidden]` — sem ser captura real, que
traria dado pessoal para o repositório. O que se prova aqui: cada leitor pega o
campo certo, sem duplicar o texto do leitor de tela, e não faz nada além de ler.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

LINKEDIN_JS = (Path(__file__).resolve().parents[2] / "extensao" / "linkedin.js"
               ).read_text(encoding="utf-8")


@pytest.fixture
def pagina(carregar_fixture):
    p = carregar_fixture("linkedin_perfil.html")
    p.add_script_tag(content=LINKEDIN_JS)
    return p


def test_titulo(pagina):
    assert pagina.evaluate("lerTitulo()") == "Coordenador de Dados | SQL, Python, Power BI"


def test_sobre_sem_o_texto_duplicado_do_leitor_de_tela(pagina):
    sobre = pagina.evaluate("lerSobre()")
    assert sobre.startswith("Engenheiro de Dados com dois anos")
    assert sobre.count("Engenheiro de Dados") == 1, sobre


def test_experiencias(pagina):
    exps = pagina.evaluate("lerExperiencias()")
    assert [e["cargo"] for e in exps] == ["Coordenador de Dados", "Analista Pleno de BI"]
    assert [e["empresa"] for e in exps] == ["Acme", "Beta BI"]
    assert exps[0]["periodo"].startswith("ago de 2025")
    assert "Databricks" in exps[0]["descricao"]


def test_formacao_e_competencias(pagina):
    assert pagina.evaluate("lerFormacao()") == [
        {"instituicao": "FIAP", "curso": "Tecnólogo, Defesa Cibernética"}]
    assert pagina.evaluate("lerCompetencias(document.getElementById('skills').closest('section'))") \
        == ["SQL", "Power BI"]


def test_fora_da_pagina_de_perfil_nao_desenha_botao(pagina):
    """A fixture é carregada num `about:blank`/arquivo local, que não é `/in/*`:
    o botão só existe na página do perfil."""
    assert pagina.query_selector("#aija-analisar") is None


def test_nao_altera_a_pagina(pagina):
    antes = pagina.evaluate("document.querySelector('main').innerHTML")
    pagina.evaluate("lerTitulo(); lerSobre(); lerExperiencias(); lerFormacao()")
    assert pagina.evaluate("document.querySelector('main').innerHTML") == antes
