"""As perguntas da Gupy estão na página pública, não atrás do login.

Eu havia concluído o contrário porque clicar em "Candidatar-se" redireciona para
`/candidates/signin`. O **formulário** está atrás do login; os **dados** não. A
página é Next.js e embute o payload inteiro em `__NEXT_DATA__`, com
`job.questionForm` completo — título, tipo, opções, obrigatoriedade e a flag
`disqualifying`.

A distinção que este módulo precisa acertar: `questionForm: null` significa
"vaga sem formulário customizado", não "não consegui ler". Medido em 20 vagas de
dados, 19 são assim. Tratar isso como falha faria o cartão pedir atenção humana
em 95% das vagas sem motivo nenhum.
"""
import json

import pytest

from jobapplier.applicators.descoberta import StatusDescoberta
from jobapplier.applicators.gupy_perguntas import (
    descobrir_perguntas,
    eliminatorias,
)

PERGUNTAS = [
    {"questionId": 2708962, "order": 1, "required": True,
     "title": "Reside na Cidade de Guarulhos ou tem fácil acesso?",
     "type": "SELECT", "options": [{"label": "Sim"}, {"label": "Não"}],
     "disqualifying": False},
    {"questionId": 2708963, "order": 2, "required": True,
     "title": "Aceita trabalhar presencialmente?",
     "type": "SELECT", "options": [{"label": "Sim"}, {"label": "Não"}],
     "disqualifying": True},
    {"questionId": 2708966, "order": 5, "required": True,
     "title": "Por favor, informe sua pretensão salarial.",
     "type": "TEXT", "options": [], "disqualifying": False},
]


def _pagina(job: dict) -> str:
    payload = {"props": {"pageProps": {"job": job}}}
    return (f'<html><body><script id="__NEXT_DATA__" type="application/json">'
            f'{json.dumps(payload, ensure_ascii=False)}</script></body></html>')


class _Resposta:
    def __init__(self, texto="", status=200):
        self.text = texto
        self.status_code = status


@pytest.fixture
def responder(monkeypatch):
    def instalar(resposta):
        import jobapplier.applicators.gupy_perguntas as mod
        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resposta)
    return instalar


# ── Caso com perguntas ────────────────────────────────────────────────────────

def test_le_as_perguntas_da_pagina_publica(responder):
    responder(_Resposta(_pagina({"status": "published",
                                 "questionForm": {"formId": 1, "questions": PERGUNTAS}})))
    d = descobrir_perguntas("https://acme.gupy.io/job/tok")

    assert d.ok
    assert len(d.perguntas) == 3
    assert d.perguntas[0].label.startswith("Reside na Cidade")
    assert all(p.obrigatoria for p in d.perguntas)


def test_tipos_sao_traduzidos_para_o_vocabulario_do_projeto(responder):
    """Sem tradução, `_auto_answer` receberia 'SELECT' onde espera
    'multi_value_single_select' e não responderia nada."""
    responder(_Resposta(_pagina({"questionForm": {"questions": PERGUNTAS}})))
    d = descobrir_perguntas("https://acme.gupy.io/job/tok")

    assert d.perguntas[0].tipo == "multi_value_single_select"
    assert d.perguntas[2].tipo == "input_text"


def test_opcoes_viram_label_e_value(responder):
    responder(_Resposta(_pagina({"questionForm": {"questions": PERGUNTAS}})))
    opcoes = descobrir_perguntas("https://acme.gupy.io/job/tok").perguntas[0].opcoes

    assert [o["label"] for o in opcoes] == ["Sim", "Não"]
    assert all(o["value"] for o in opcoes), "value vazio quebra o casamento da resposta"


def test_pergunta_sem_titulo_e_descartada(responder):
    responder(_Resposta(_pagina({"questionForm": {"questions": [
        {"questionId": 1, "title": "", "type": "TEXT"},
        {"questionId": 2, "title": "Válida?", "type": "TEXT"},
    ]}})))
    d = descobrir_perguntas("https://acme.gupy.io/job/tok")

    assert len(d.perguntas) == 1


# ── Ausência de perguntas é sucesso, não falha ────────────────────────────────

@pytest.mark.parametrize("job", [
    {"questionForm": None},
    {"questionForm": {}},
    {"questionForm": {"questions": []}},
    {},
])
def test_vaga_sem_formulario_e_sucesso_com_lista_vazia(responder, job):
    """19 de 20 vagas são assim. Tratar como falha faria o cartão pedir atenção
    humana em 95% dos casos sem motivo."""
    responder(_Resposta(_pagina({**job, "status": "published"})))
    d = descobrir_perguntas("https://acme.gupy.io/job/tok")

    assert d.status is StatusDescoberta.SUCESSO
    assert d.perguntas == []


# ── Falhas de verdade ─────────────────────────────────────────────────────────

def test_pagina_sem_next_data_e_falha_de_leitura(responder):
    """Se a Gupy trocar de framework, isso precisa ser distinguível de 'vaga sem
    perguntas' — senão a mudança passa despercebida para sempre."""
    responder(_Resposta("<html><body>página normal</body></html>"))
    d = descobrir_perguntas("https://acme.gupy.io/job/tok")

    assert d.status is StatusDescoberta.RESPOSTA_INVALIDA
    assert "__NEXT_DATA__" in d.detalhe


def test_next_data_ilegivel(responder):
    responder(_Resposta('<script id="__NEXT_DATA__">{quebrado</script>'))
    assert descobrir_perguntas("https://acme.gupy.io/job/x").status \
        is StatusDescoberta.RESPOSTA_INVALIDA


def test_404_e_vaga_nao_encontrada(responder):
    responder(_Resposta("", status=404))
    assert descobrir_perguntas("https://acme.gupy.io/job/x").status \
        is StatusDescoberta.VAGA_NAO_ENCONTRADA


def test_500_e_retentavel(responder):
    responder(_Resposta("", status=503))
    d = descobrir_perguntas("https://acme.gupy.io/job/x")
    assert d.status is StatusDescoberta.FALHA_TEMPORARIA
    assert d.retentavel


def test_erro_de_rede_e_retentavel(monkeypatch):
    import jobapplier.applicators.gupy_perguntas as mod

    def explode(*a, **k):
        raise mod.requests.RequestException("timeout")

    monkeypatch.setattr(mod.requests, "get", explode)
    assert descobrir_perguntas("https://acme.gupy.io/job/x").retentavel


def test_vaga_encerrada(responder):
    responder(_Resposta(_pagina({"status": "closed",
                                 "questionForm": {"questions": PERGUNTAS}})))
    assert descobrir_perguntas("https://acme.gupy.io/job/x").status \
        is StatusDescoberta.VAGA_ENCERRADA


def test_link_vazio_nao_faz_requisicao():
    assert descobrir_perguntas("").status is StatusDescoberta.RESPOSTA_INVALIDA


# ── Eliminatórias ─────────────────────────────────────────────────────────────

def test_perguntas_eliminatorias_sao_destacadas():
    """A Gupy declara quais respostas descartam o candidato na hora. Errar uma
    dessas não é resposta fraca — é descarte, e merece mais atenção que dez
    opcionais."""
    html = _pagina({"questionForm": {"questions": PERGUNTAS}})
    assert eliminatorias(None, html) == ["Aceita trabalhar presencialmente?"]


def test_sem_html_nao_ha_eliminatorias():
    assert eliminatorias(None, "") == []
    assert eliminatorias(None, "<html>sem next data</html>") == []


# ── Contrato com o resto do projeto ───────────────────────────────────────────

def test_devolve_o_mesmo_contrato_do_greenhouse():
    """Cartão e `_auto_answer` consomem os dois sem saber de qual plataforma
    veio — se os contratos divergirem, um dos dois quebra em produção."""
    import jobapplier.applicators.gupy_perguntas as gupy
    from jobapplier.applicators.descoberta import Descoberta, Pergunta

    assert gupy.Descoberta is Descoberta
    assert gupy.Pergunta is Pergunta


@pytest.mark.live
def test_pagina_real_continua_expondo_o_formulario():
    """Só sob demanda (`pytest -m live`). Página pública, sem login, sem enviar
    nada — dentro do que a invariante 6 permite."""
    import requests

    from jobapplier.applicators.gupy_perguntas import CABECALHOS

    r = requests.get("https://employability-portal.gupy.io/api/v1/jobs",
                     params={"jobName": "dados", "limit": 5},
                     headers={"Accept": "application/json", **CABECALHOS}, timeout=25)
    vagas = r.json().get("data", [])
    assert vagas, "a API parou de devolver vagas"

    d = descobrir_perguntas(vagas[0]["jobUrl"])
    assert d.ok, f"leitura falhou: {d.status} {d.detalhe}"
