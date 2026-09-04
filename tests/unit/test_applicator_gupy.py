"""O parser de link do applicator da Gupy recusava 100% das vagas coletadas.

Mesma classe de defasagem que zerava o coletor, e igualmente silenciosa: em vez
de um erro visível, cada vaga virava um `falha_automacao` individual, indistinguível
de "o formulário mudou". Foi assim que 67 das 293 tentativas históricas morreram
em parser de link.

Os dois formatos convivem de propósito: coleta por empresa monta `/jobs/{id}`, o
portal devolve `/job/{token base64}`.
"""
import base64
import json

import pytest

from jobapplier.applicators.gupy import _id_do_token, _parse_link


def _token(**dados) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(dados).encode("utf-8")
    ).decode("ascii").rstrip("=")


# ── Formato do portal (atual) ─────────────────────────────────────────────────

def test_link_real_do_portal():
    """Link como a API devolve hoje, com rastreamento na query string."""
    link = ("https://ipiranga.gupy.io/job/"
            "eyJqb2JJZCI6MTIxNTA2MDcsInNvdXJjZSI6Imd1cHlfcG9ydGFsIn0="
            "?jobBoardSource=gupy_portal")
    assert _parse_link(link) == ("ipiranga", "12150607")


def test_token_sem_padding():
    """base64 urlsafe em URL costuma vir sem '='; sem recompor, a decodificação
    falha e a vaga inteira é perdida."""
    link = f"https://acme.gupy.io/job/{_token(jobId=987, source='gupy_portal')}"
    assert _parse_link(link) == ("acme", "987")


def test_query_string_nao_entra_no_token():
    esperado = ("empresa", "555")
    assert _parse_link(
        f"https://empresa.gupy.io/job/{_token(jobId=555)}?utm_source=x&ref=y"
    ) == esperado


# ── Formato antigo ────────────────────────────────────────────────────────────

def test_formato_antigo_continua_valendo():
    """A coleta por empresa ainda monta este formato."""
    assert _parse_link("https://acme.gupy.io/jobs/12345") == ("acme", "12345")


def test_singular_e_plural():
    assert _parse_link("https://acme.gupy.io/job/12345") == ("acme", "12345")


# ── Recusas ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("link", [
    "",
    None,
    "https://acme.gupy.io/",
    "https://acme.gupy.io/vagas/123",
    "https://boards.greenhouse.io/acme/jobs/123",
    "não é uma url",
])
def test_link_que_nao_e_vaga_gupy_e_recusado(link):
    assert _parse_link(link) is None


def test_token_ilegivel_nao_derruba_a_esteira():
    """Link estranho tem que virar vaga sem automação, nunca exceção — a esteira
    processa uma fila e não pode morrer no item 3 de 300."""
    assert _parse_link("https://acme.gupy.io/job/@@@nao-e-base64@@@") is None
    assert _id_do_token("!!!") is None


def test_token_valido_mas_sem_jobid():
    """base64 correto de um JSON que não tem o campo esperado."""
    assert _parse_link(f"https://acme.gupy.io/job/{_token(source='x')}") is None


def test_token_que_decodifica_para_lista():
    assert _id_do_token(
        base64.urlsafe_b64encode(b'[1,2,3]').decode().rstrip("=")
    ) is None


# ── Contrato ──────────────────────────────────────────────────────────────────

def test_todo_link_produzido_pelo_coletor_e_aceito_pelo_applicator():
    """Coletor e applicator precisam concordar sobre o formato do link.

    Estavam discordando: o coletor passou a produzir `/job/{token}` e o
    applicator só aceitava `/jobs/{id}`. Nenhum teste cruzava os dois, então a
    incompatibilidade só apareceria como falha em produção, uma vaga por vez.
    """
    from jobapplier.collectors.gupy import _para_vaga

    item = {
        "id": 12147158,
        "name": "Engenheiro de Dados",
        "careerPageName": "Acme",
        "jobUrl": ("https://acme.gupy.io/job/"
                   "eyJqb2JJZCI6MTIxNDcxNTgsInNvdXJjZSI6Imd1cHlfcG9ydGFsIn0="),
        "workplaceType": "remote",
    }
    vaga = _para_vaga(item)
    assert vaga is not None

    parseado = _parse_link(vaga.link)
    assert parseado is not None, "o applicator tem que aceitar o link do coletor"
    assert parseado[1] == vaga.fonte_vaga_id, "o id extraído tem que bater"
