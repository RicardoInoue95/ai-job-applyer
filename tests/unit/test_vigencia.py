"""A vaga ainda existe? E, sobretudo, quando NÃO se sabe.

Amostra de 40 vagas do Greenhouse na fila: 9 encerradas, 22%. Somadas as 8 da
inhire, todas mortas, a fila apresentava como oportunidade algo que já acabou —
o usuário escolhe o cartão, lê o dossiê, decide, e leva 404.

O teste que mais importa aqui não é o que detecta vaga morta: é o que garante
que **erro de rede não mata vaga viva**. Encerrar por engano some com a vaga da
fila, e recuperá-la exige saber que existiu.
"""
from types import SimpleNamespace

import pytest

from jobapplier import vigencia
from jobapplier.vigencia import Vigencia, checar


def _vaga(plataforma="greenhouse", link="https://x/y"):
    return SimpleNamespace(id=1, plataforma=plataforma, link=link,
                           empresa="acme", titulo="Data Engineer", score=80)


# ── A direção segura ──────────────────────────────────────────────────────────

def test_erro_de_rede_nao_encerra(monkeypatch):
    def explode(*a, **k):
        raise ConnectionError("rede caiu")

    monkeypatch.setattr(vigencia.requests, "get", explode)
    estado, motivo = checar(_vaga("lever", "https://jobs.lever.co/x/"
                                  "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
    assert estado is Vigencia.INDETERMINADA
    assert "ConnectionError" in motivo


def test_plataforma_sem_checagem_e_indeterminada():
    """LinkedIn fica de fora de propósito: checar exigiria a sessão salva, e
    cada leitura gasta cota de detecção de uma conta que é a identidade
    profissional real do usuário (invariante 6)."""
    estado, motivo = checar(_vaga("linkedin"))
    assert estado is Vigencia.INDETERMINADA
    assert "linkedin" in motivo
    assert not vigencia.suportada("linkedin")


@pytest.mark.parametrize("codigo", [500, 502, 429, 403])
def test_http_inesperado_nao_encerra(monkeypatch, codigo):
    """5xx e 429 são a plataforma com problema, não a vaga tendo acabado."""
    monkeypatch.setattr(vigencia.requests, "get",
                        lambda *a, **k: SimpleNamespace(status_code=codigo, text=""))
    estado, _ = checar(_vaga("lever", "https://jobs.lever.co/x/"
                             "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
    assert estado is Vigencia.INDETERMINADA


def test_vaga_sem_link_nao_encerra():
    estado, _ = checar(_vaga("gupy", ""))
    assert estado is Vigencia.INDETERMINADA


# ── Lever ─────────────────────────────────────────────────────────────────────

LEVER_OK = "https://jobs.lever.co/spotify/759f6c62-e450-4112-9db6-0c01eef47c76"


@pytest.mark.parametrize("codigo,esperado", [
    (404, Vigencia.ENCERRADA), (200, Vigencia.ABERTA)])
def test_lever_le_o_status_http(monkeypatch, codigo, esperado):
    monkeypatch.setattr(vigencia.requests, "get",
                        lambda *a, **k: SimpleNamespace(status_code=codigo, text=""))
    assert checar(_vaga("lever", LEVER_OK))[0] is esperado


def test_lever_com_link_de_outra_plataforma():
    estado, motivo = checar(_vaga("lever", "https://boards.greenhouse.io/a/jobs/1"))
    assert estado is Vigencia.INDETERMINADA
    assert "Lever" in motivo


# ── Gupy ──────────────────────────────────────────────────────────────────────

def _pagina_gupy(status: str) -> str:
    return ('<html><body>Vagas encerradas · filtro'
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"job":{"name":"X","status":"'
            f'{status}'
            '"}}}}</script></body></html>')


@pytest.mark.parametrize("status,esperado", [
    ("published", Vigencia.ABERTA),
    ("canceled", Vigencia.ENCERRADA),
    ("closed", Vigencia.ENCERRADA),
    ("draft", Vigencia.ENCERRADA),
])
def test_gupy_le_o_status_estruturado(monkeypatch, status, esperado):
    """A palavra "encerrada" aparece no HTML de TODA vaga da Gupy, aberta ou
    não — é rótulo de interface. Procurá-la no texto marcaria o acervo inteiro
    como morto; o dado real está no __NEXT_DATA__."""
    monkeypatch.setattr(vigencia.requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, text=_pagina_gupy(status)))
    assert checar(_vaga("gupy", "https://x.gupy.io/job/abc"))[0] is esperado


def test_gupy_sem_next_data_nao_encerra(monkeypatch):
    monkeypatch.setattr(vigencia.requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, text="<html>página de manutenção</html>"))
    estado, motivo = checar(_vaga("gupy", "https://x.gupy.io/job/abc"))
    assert estado is Vigencia.INDETERMINADA
    assert "__NEXT_DATA__" in motivo


def test_gupy_json_quebrado_nao_encerra(monkeypatch):
    monkeypatch.setattr(vigencia.requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200,
        text='<script id="__NEXT_DATA__">{isto nao e json</script>'))
    assert checar(_vaga("gupy", "https://x.gupy.io/job/a"))[0] is Vigencia.INDETERMINADA


# ── inhire ────────────────────────────────────────────────────────────────────

def test_inhire_presente_na_lista_esta_aberta(monkeypatch):
    monkeypatch.setattr(vigencia.requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, json=lambda: [{"id": "abc-123"}]))
    assert checar(_vaga("inhire", "https://radix.inhire.app/vagas/abc-123")
                  )[0] is Vigencia.ABERTA


def test_inhire_ausente_da_lista_esta_encerrada(monkeypatch):
    monkeypatch.setattr(vigencia.requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, json=lambda: [{"id": "outra"}]))
    assert checar(_vaga("inhire", "https://radix.inhire.app/vagas/abc-123")
                  )[0] is Vigencia.ENCERRADA


def test_inhire_sem_tenant_no_link():
    estado, motivo = checar(_vaga("inhire", "https://inhire.app/vagas/abc"))
    assert estado is Vigencia.INDETERMINADA
    assert "tenant" in motivo


# ── Contrato com a varredura ──────────────────────────────────────────────────

def test_varredura_so_marca_o_que_e_encerrada():
    """INDETERMINADA nunca pode virar 'encerrada' no banco."""
    import ast
    from pathlib import Path

    fonte = (Path(__file__).resolve().parents[2] / "scripts" / "varredura.py"
             ).read_text(encoding="utf-8")
    ast.parse(fonte)
    assert 'vaga.status = "encerrada"' in fonte
    # A lista que vai para o banco só é alimentada no ramo de ENCERRADA.
    trecho = fonte[fonte.index("if estado is Vigencia.ENCERRADA:"):]
    assert "encerradas.append" in trecho[:300]


def test_varredura_relata_por_padrao():
    """Encerrar em massa é irreversível na prática: a vaga some da fila."""
    import inspect
    import sys as _sys
    from pathlib import Path

    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import varredura

    assert inspect.signature(varredura.varrer).parameters["aplicar"].default is False
