"""Módulo 14 — Lever. Preenche tudo e para no hCaptcha.

O registro do projeto dizia que o Lever era "mesma família do Greenhouse:
público, sem login, **sem CAPTCHA**", e era essa frase que o fazia parecer o
melhor retorno por hora disponível. Medido no formulário real de
`jobs.lever.co/<slug>/<id>/apply`: `<div class="h-captcha">` com sitekey, dois
iframes, campo oculto `h-captcha-response` e JS que prende o envio ao token.

Estes testes travam as duas coisas que isso implica: o applicator nunca devolve
"enviada" sozinho, e nada nele contorna o desafio.
"""
import inspect

import pytest

from jobapplier.applicators import lever
from jobapplier.applicators.base import (
    AGUARDANDO_VERIFICACAO,
    ENVIADA_CONFIRMADA,
    suportada,
)

# ── Identidade a partir do link ───────────────────────────────────────────────

@pytest.mark.parametrize("link,esperado", [
    ("https://jobs.lever.co/spotify/759f6c62-e450-4112-9db6-0c01eef47c76",
     ("spotify", "759f6c62-e450-4112-9db6-0c01eef47c76")),
    ("https://jobs.lever.co/spotify/759f6c62-e450-4112-9db6-0c01eef47c76/apply",
     ("spotify", "759f6c62-e450-4112-9db6-0c01eef47c76")),
    ("http://jobs.lever.co/acme-tech/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
     ("acme-tech", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")),
])
def test_extrai_slug_e_id(link, esperado):
    assert lever.extrair_identidade(link) == esperado


@pytest.mark.parametrize("link", [
    "", None,
    "https://boards.greenhouse.io/adyen/jobs/8042142",
    "https://jobs.lever.co/spotify",
    "https://jobs.lever.co/spotify/nao-e-uuid",
])
def test_link_alheio_nao_vira_identidade(link):
    """Link de outra plataforma caindo aqui produziria uma URL inventada, e a
    candidatura falharia num lugar difícil de diagnosticar."""
    assert lever.extrair_identidade(link) is None


# ── O contrato que o hCaptcha impõe ───────────────────────────────────────────

def test_lever_esta_no_registro():
    assert suportada("lever")


def _codigo_sem_prosa() -> str:
    """Fonte do módulo sem docstring e sem comentário.

    Precisa existir porque a docstring deste applicator **descreve a barreira**:
    ela cita `h-captcha-response`, `sitekey` e `navigator.webdriver` para
    explicar o que NÃO se faz. Procurar essas palavras no arquivo inteiro pune
    justamente a documentação honesta — e "solve" ainda casa dentro de
    "resolvendo".
    """
    import ast
    import io
    import tokenize

    fonte = inspect.getsource(lever)
    arvore = ast.parse(fonte)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            no.value = ""
    sem_docstring = ast.unparse(arvore)
    linhas = []
    for tok in tokenize.generate_tokens(io.StringIO(sem_docstring).readline):
        if tok.type != tokenize.COMMENT:
            linhas.append(tok.string)
    return " ".join(linhas)


def test_nunca_devolve_enviada_sem_o_gancho():
    """`ENVIADA_CONFIRMADA` só aparece dentro do ramo do `ao_verificar`, que é a
    sessão assistida onde o candidato resolveu o desafio e clicou."""
    fonte = inspect.getsource(lever.apply)
    antes = fonte[:fonte.index("if ao_verificar is not None")]
    assert "ENVIADA_CONFIRMADA" not in antes


def test_desfecho_padrao_e_aguardando_verificacao():
    assert "AGUARDANDO_VERIFICACAO" in inspect.getsource(lever.apply)


def test_os_dois_status_sao_os_do_registro():
    """Se alguém renomear a constante, o teste acima passaria a olhar um nome
    que não existe mais."""
    assert AGUARDANDO_VERIFICACAO == "aguardando_verificacao"
    assert ENVIADA_CONFIRMADA == "enviada_confirmada"


@pytest.mark.parametrize("proibido", [
    "hcaptcha.render", "h-captcha-response", "sitekey", "bypass",
    "navigator.webdriver", "stealth", "2captcha", "anticaptcha",
])
def test_nao_contorna_o_desafio(proibido):
    """Mesma régua do Turnstile da Gupy: preencher o formulário é assistência,
    resolver o desafio por ele é evasão de detecção."""
    assert proibido not in _codigo_sem_prosa()


def test_nao_clica_em_enviar():
    """O único clique é na sugestão do autocomplete de localização."""
    cliques = [ln.strip() for ln in inspect.getsource(lever).splitlines()
               if ".click()" in ln and not ln.strip().startswith("#")]
    assert cliques == ["sugestao.click()"], cliques


def test_headless_e_o_padrao():
    p = inspect.signature(lever.apply).parameters
    assert p["visivel"].default is False
    assert p["ao_verificar"].default is None


def test_mesma_assinatura_do_greenhouse():
    """A sessão assistida chama os dois pelo mesmo caminho; assinatura diferente
    quebraria só em produção, na primeira vaga do Lever."""
    from jobapplier.applicators import greenhouse

    assert (list(inspect.signature(lever.apply).parameters)
            == list(inspect.signature(greenhouse.apply).parameters))


# ── Perguntas customizadas ────────────────────────────────────────────────────

class _CampoFake:
    def __init__(self, tipo, rotulo):
        self._tipo, self._rotulo = tipo, rotulo

    def get_attribute(self, nome):
        return self._tipo if nome == "type" else (
            self._rotulo if nome == "aria-label" else None)

    def evaluate(self, _js):
        return self._rotulo


class _PaginaFake:
    def __init__(self, campos):
        self._campos = campos

    def query_selector_all(self, _sel):
        return self._campos


def test_pergunta_sensivel_nao_entra_na_lista():
    """Pronomes e afins não são "pergunta que falta responder" — são recusa
    deliberada. Contá-las infla o bloqueio e esconde o que de fato falta."""
    pagina = _PaginaFake([
        _CampoFake("text", "Quantos anos de experiência com Python?"),
        _CampoFake("checkbox", "What are your pronouns?"),
        _CampoFake("text", "Qual sua identidade de gênero?"),
    ])
    assert lever.perguntas_do_formulario(pagina) == [
        "Quantos anos de experiência com Python?"]


def test_campo_oculto_nao_e_pergunta():
    pagina = _PaginaFake([_CampoFake("hidden", "cards uuid interno")])
    assert lever.perguntas_do_formulario(pagina) == []


def test_nao_repete_pergunta():
    pagina = _PaginaFake([_CampoFake("text", "Mesma pergunta")] * 3)
    assert lever.perguntas_do_formulario(pagina) == ["Mesma pergunta"]
