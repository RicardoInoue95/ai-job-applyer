"""Matriz de contrato do Greenhouse: 20 cenários de formulário.

Esta é a camada que faltava. A cobertura estava concentrada onde o risco é menor
e ausente no ponto irreversível — o applicator, que age em nome do usuário sobre
HTML e APIs de terceiros que mudam sem aviso.

Não toca a rede: cada cenário injeta a resposta que a API do Greenhouse
devolveria. Um cenário novo é uma entrada em `fixtures/greenhouse_matriz.py`,
não um arquivo novo de teste.

O que a matriz garante, por grupo:

- suportado    → a automação consegue preencher e diz isso
- intervenção  → a automação RECUSA e explica por quê, com código distinto
- falha        → a avaliação é indeterminada, nunca zero disfarçado de medição
"""
import json

import pytest

from jobapplier.applicators import greenhouse
from jobapplier.applicators.base import avaliar_confirmacao
from jobapplier.applicators.descoberta import Prontidao, StatusDescoberta

from .fixtures.greenhouse_matriz import SUBMISSAO, TODOS

pytestmark = pytest.mark.e2e

CURRICULO = {
    "nome": "Ricardo Inoue",
    "email": "info@exemplo.com",
    "telefone": "+55 11 90000-0000",
    "linkedin": "https://linkedin.com/in/exemplo",
    "github": "https://github.com/exemplo",
    "localizacao": "São Paulo, SP",
    "tecnologias": ["Python", "SQL", "Snowflake", "dbt"],
    "idiomas": [{"nome": "Inglês", "nivel": "Avançado"}],
    "experiencias": [
        {"empresa": "Empresa Atual", "cargo": "Analytics Engineer",
         "data_inicio": "01/2023", "data_fim": None, "tecnologias": ["Snowflake"]},
    ],
}


class RespostaFake:
    """Resposta HTTP mínima, com a superfície que `descobrir_perguntas` usa."""

    def __init__(self, status: int, corpo):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        if isinstance(self._corpo, str):
            # Corpo não-JSON: o requests levantaria aqui.
            raise json.JSONDecodeError("não é JSON", self._corpo, 0)
        return self._corpo


@pytest.fixture
def api(monkeypatch):
    """Injeta a resposta da API do Greenhouse. Nenhuma chamada de rede sai."""

    def _configurar(cenario):
        def falso_get(*_args, **_kwargs):
            if cenario.excecao is not None:
                raise cenario.excecao
            return RespostaFake(cenario.http_status, cenario.corpo)

        monkeypatch.setattr(greenhouse.requests, "get", falso_get)

    return _configurar


def _vaga():
    import types

    return types.SimpleNamespace(
        id=1, plataforma="greenhouse",
        titulo="Data Engineer", empresa="acme",
        link="https://boards.greenhouse.io/acme/jobs/123456",
        normalizado_json={"tecnologias": ["Python", "SQL"], "senioridade": "Pleno"},
    )


def _avaliar(cenario):
    dados = {"cpf": "123.456.789-00"} if cenario.cpf_configurado else {}
    return greenhouse.avaliar_preenchimento(_vaga(), CURRICULO, dados)


IDS = [c.id for c in TODOS]


# ── A matriz ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_status_de_descoberta(cenario, api):
    api(cenario)
    assert _avaliar(cenario)["discovery_status"] == cenario.discovery_status, cenario.descricao


@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_prontidao(cenario, api):
    api(cenario)
    assert _avaliar(cenario)["application_readiness"] == cenario.readiness, cenario.descricao


@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_confianca_so_existe_com_descoberta_bem_sucedida(cenario, api):
    """A regra dura do contrato.

    Falha de leitura devolve None, nunca 0.0: zero pareceria uma medição válida
    dizendo "não consigo preencher", quando a verdade é "não sei".
    """
    api(cenario)
    confianca = _avaliar(cenario)["application_confidence"]

    if cenario.confianca_e_none:
        assert confianca is None, cenario.descricao
    else:
        assert confianca is not None, cenario.descricao
        assert 0.0 <= confianca <= 1.0


@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_motivo_do_bloqueio(cenario, api):
    api(cenario)
    assert _avaliar(cenario)["blocking_reason"] == cenario.blocking_reason, cenario.descricao


@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_retentavel_marcado_apenas_em_falha_transitoria(cenario, api):
    api(cenario)
    assert _avaliar(cenario)["retentavel"] is cenario.retentavel, cenario.descricao


@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_formato_da_avaliacao_e_estavel(cenario, api):
    """Todo cenário produz o mesmo conjunto de chaves — o consumidor não precisa
    de `.get()` defensivo, e o dado no banco é comparável entre execuções."""
    api(cenario)
    a = _avaliar(cenario)
    assert {"plataforma", "discovery_status", "http_status", "known_required",
            "unknown_required", "known_optional", "unknown_optional",
            "manual_questions", "blockers", "application_confidence",
            "application_readiness", "blocking_reason", "retentavel"} <= set(a)


@pytest.mark.parametrize(
    "cenario", [c for c in TODOS if c.min_obrigatorias_desconhecidas], ids=lambda c: c.id
)
def test_perguntas_manuais_sao_listadas(cenario, api):
    """Não basta recusar: é preciso dizer QUAL campo exige o humano."""
    api(cenario)
    a = _avaliar(cenario)
    assert a["unknown_required"] >= cenario.min_obrigatorias_desconhecidas
    assert a["manual_questions"], cenario.descricao


# ── Invariantes que atravessam a matriz ───────────────────────────────────────

def test_todo_cenario_suportado_fica_pronto(api):
    for cenario in (c for c in TODOS if c.grupo == "suportado"):
        api(cenario)
        a = _avaliar(cenario)
        assert a["application_readiness"] == Prontidao.PRONTA, cenario.id
        assert a["application_confidence"] == 1.0, cenario.id
        assert not a["blockers"], cenario.id


def test_nenhum_cenario_de_falha_recebe_confianca(api):
    for cenario in (c for c in TODOS if c.grupo == "falha_leitura"):
        api(cenario)
        a = _avaliar(cenario)
        assert a["application_confidence"] is None, cenario.id
        assert a["application_readiness"] == Prontidao.INDETERMINADA, cenario.id


def test_bloqueadores_tem_codigos_distintos(api):
    """CPF ausente, work authorization e tipo não suportado exigem ações
    diferentes: configurar, desistir, ou implementar suporte."""
    codigos = set()
    for cenario in (c for c in TODOS if c.readiness == "bloqueada"):
        api(cenario)
        a = _avaliar(cenario)
        assert a["blockers"], cenario.id
        codigos.add(a["blockers"][0]["codigo"])
    assert len(codigos) >= 3, f"bloqueadores colapsando num código só: {codigos}"


def test_matriz_cobre_os_tres_grupos():
    grupos = {c.grupo for c in TODOS}
    assert grupos == {"suportado", "intervencao", "falha_leitura"}
    assert len(TODOS) >= 18, "a matriz encolheu"


def test_todo_status_de_descoberta_aparece_na_matriz():
    """Sem isto, um status novo poderia nascer sem nenhum cenário exercitando."""
    cobertos = {c.discovery_status for c in TODOS}
    assert cobertos == {str(s) for s in StatusDescoberta}


# ── Desfechos de submissão ────────────────────────────────────────────────────

@pytest.mark.parametrize("cenario", SUBMISSAO, ids=lambda c: c.id)
def test_desfecho_de_submissao(cenario):
    status, motivo = avaliar_confirmacao(
        cenario.sinais_fortes,
        perguntas_manuais=cenario.perguntas_manuais,
        sinais_fracos=cenario.sinais_fracos,
    )
    assert status == cenario.status_esperado, f"{cenario.descricao}: {motivo}"


def test_apenas_um_cenario_de_submissao_confirma():
    """Confirmação tem de ser exceção bem provada, não o caso comum."""
    confirmados = [c for c in SUBMISSAO if c.status_esperado == "enviada_confirmada"]
    assert len(confirmados) == 1


# ── O número nunca pode contradizer o gate ────────────────────────────────────

def test_cobertura_de_opcionais_nunca_compensa_obrigatoria_faltando():
    """Regressão real da média ponderada 0.8/0.2.

    Um formulário com 9/10 obrigatórias e TODAS as opcionais pontuava 0.92,
    acima dos 0.80 de um formulário com todas as obrigatórias e nenhuma
    opcional — quando o segundo é o único dos dois que pode ser submetido.
    """
    from jobapplier.applicators.descoberta import (
        Descoberta,
        StatusDescoberta,
        montar_avaliacao,
    )

    ok = Descoberta(StatusDescoberta.SUCESSO, http_status=200)
    completo = montar_avaliacao(
        "greenhouse", ok,
        obrigatorias_conhecidas=["r1", "r2"],
        opcionais_desconhecidas=[f"o{i}" for i in range(5)],
    )
    incompleto = montar_avaliacao(
        "greenhouse", ok,
        obrigatorias_conhecidas=[f"r{i}" for i in range(9)],
        obrigatorias_desconhecidas=["r9"],
        opcionais_conhecidas=["o1", "o2"],
    )

    assert completo["application_confidence"] > incompleto["application_confidence"]
    assert completo["automation_eligible"]
    assert not incompleto["automation_eligible"]


def test_faixas_de_confianca_nao_se_sobrepoem():
    """Com obrigatória faltando o teto é 0.5; sem faltar, o piso é 0.8."""
    from jobapplier.applicators.descoberta import (
        Descoberta,
        StatusDescoberta,
        montar_avaliacao,
    )

    ok = Descoberta(StatusDescoberta.SUCESSO, http_status=200)
    melhor_incompleto = montar_avaliacao(
        "greenhouse", ok,
        obrigatorias_conhecidas=[f"r{i}" for i in range(99)],
        obrigatorias_desconhecidas=["r99"],
        opcionais_conhecidas=["o1"],
    )
    pior_completo = montar_avaliacao(
        "greenhouse", ok,
        obrigatorias_conhecidas=["r1"],
        opcionais_desconhecidas=[f"o{i}" for i in range(50)],
    )
    assert melhor_incompleto["application_confidence"] <= 0.5
    assert pior_completo["application_confidence"] >= 0.8


@pytest.mark.parametrize("cenario", TODOS, ids=IDS)
def test_elegibilidade_e_booleana_e_coerente_com_a_prontidao(cenario, api):
    """`automation_eligible` é o gate; nenhuma aritmética pode torná-lo True
    com obrigatória desconhecida ou bloqueador."""
    api(cenario)
    a = _avaliar(cenario)
    assert isinstance(a["automation_eligible"], bool)
    if a["automation_eligible"]:
        assert a["application_readiness"] == Prontidao.PRONTA, cenario.id
        assert a["unknown_required"] == 0, cenario.id
        assert not a["blockers"], cenario.id


def test_coberturas_expostas_separadamente(api):
    """Para ninguém ter de reinterpretar o número composto depois."""
    cenario = next(c for c in TODOS if c.grupo == "suportado")
    api(cenario)
    a = _avaliar(cenario)
    assert a["required_coverage"] == 1.0
    assert a["optional_coverage"] is not None
