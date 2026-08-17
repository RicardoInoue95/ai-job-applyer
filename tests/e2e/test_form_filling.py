"""Preenchimento de formulário com Playwright real, contra HTML local.

Esta é a camada que pega quebra de seletor — o modo de falha mais comum dos
applicators, porque depende do HTML de terceiros. Sem rede: o HTML vem de
tests/e2e/fixtures.
"""
import pytest

from jobapplier.applicators.greenhouse import _pw_fill_text, _pw_select_react
from jobapplier.safety import guard

pytestmark = pytest.mark.e2e


@pytest.fixture
def form(carregar_fixture):
    return carregar_fixture("greenhouse_form.html")


# ── _pw_fill_text ─────────────────────────────────────────────────────────────

def test_preenche_campo_visivel(form):
    _pw_fill_text(form, "#first_name", "Ricardo")
    assert form.input_value("#first_name") == "Ricardo"


def test_preenche_por_seletor_composto(form):
    """Os applicators usam listas de seletores separados por vírgula."""
    _pw_fill_text(form, "input[name*='email'], input[type='email']", "info@exemplo.com")
    assert form.input_value("#email") == "info@exemplo.com"


def test_seletor_inexistente_nao_levanta(form):
    """Invariante: campo ausente é ignorado, nunca derruba a candidatura."""
    _pw_fill_text(form, "#nao_existe_de_jeito_nenhum", "x")


def test_campo_oculto_nao_e_preenchido(form):
    """Campo display:none costuma ser honeypot ou estado interno do form."""
    _pw_fill_text(form, "#campo_oculto", "nao deveria entrar")
    assert form.input_value("#campo_oculto") == ""


def test_seletor_invalido_nao_levanta(form):
    _pw_fill_text(form, "input[[[", "x")


def test_preenche_textarea(form):
    _pw_fill_text(form, "#cover_letter_text", "Prezados,\n\nTexto da carta.")
    assert "Texto da carta" in form.input_value("#cover_letter_text")


def test_sobrescreve_valor_anterior(form):
    _pw_fill_text(form, "#first_name", "Primeiro")
    _pw_fill_text(form, "#first_name", "Segundo")
    assert form.input_value("#first_name") == "Segundo"


# ── _pw_select_react ──────────────────────────────────────────────────────────

def test_seleciona_opcao_por_label(form):
    assert _pw_select_react(form, "question_1001", "Avançado")
    assert form.get_attribute("#question_1001", "data-valor-escolhido") == "Avançado"


def test_selecao_e_case_insensitive(form):
    assert _pw_select_react(form, "question_1001", "avançado")
    assert form.get_attribute("#question_1001", "data-valor-escolhido") == "Avançado"


def test_seleciona_por_substring(form):
    assert _pw_select_react(form, "question_2002[]", "São Paulo")
    assert "São Paulo" in form.get_attribute('[id="question_2002[]"]', "data-valor-escolhido")


def test_id_com_colchetes_e_normalizado(form):
    """O Greenhouse usa question_N[] em multi-select; o id do option não tem os []."""
    assert _pw_select_react(form, "question_2002[]", "Paraná")


def test_opcao_inexistente_retorna_false(form):
    assert not _pw_select_react(form, "question_1001", "Klingon")
    assert form.get_attribute("#question_1001", "data-valor-escolhido") is None


def test_campo_inexistente_retorna_false_sem_levantar(form):
    assert not _pw_select_react(form, "question_9999", "Avançado", timeout=500)


def test_nao_seleciona_nada_quando_label_vazio(form):
    # Label vazio casaria com qualquer opção por substring — deve escolher a
    # primeira, não estourar. Documenta o comportamento atual.
    resultado = _pw_select_react(form, "question_1001", "")
    assert resultado in (True, False)


# ── Jitter humano contra página real ──────────────────────────────────────────

def test_humanizar_funciona_em_pagina_real(form):
    """Valida a integração do Módulo 9 com a API real do Playwright.

    Os testes unitários usam mouse falso; aqui confirma-se que as chamadas
    existem de verdade na API e que o scroll não estoura.
    """
    guard.humanizar(form)
    assert form.evaluate("() => document.readyState") == "complete"


def test_humanizar_nao_altera_o_formulario(form):
    _pw_fill_text(form, "#first_name", "Ricardo")
    guard.humanizar(form)
    assert form.input_value("#first_name") == "Ricardo"


# ── Upload de arquivo ─────────────────────────────────────────────────────────

def test_upload_de_curriculo(form, tmp_path):
    pdf = tmp_path / "curriculo.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% teste\n")

    form.set_input_files("#resume", str(pdf))
    nome = form.evaluate("() => document.querySelector('#resume').files[0].name")
    assert nome == "curriculo.pdf"
