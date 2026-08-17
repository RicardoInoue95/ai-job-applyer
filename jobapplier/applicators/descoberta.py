"""Contrato de descoberta de formulário e classificação de bloqueadores.

Descoberta e avaliação eram implícitas: uma função devolvia `list[dict]` e o
chamador não tinha como distinguir "formulário sem perguntas customizadas" de
"não consegui ler a vaga". As duas viravam lista vazia — e zero campos era
interpretado como formulário simples, rendendo confiança máxima a uma vaga que
sequer foi aberta.

A regra que este módulo impõe:

    application_confidence só existe quando a descoberta teve sucesso.

Nos demais casos a confiança é ``None``, nunca ``0.0``. Zero parece uma medição
válida e diz "não consigo preencher"; ``None`` diz "não sei", que é a verdade.
São situações operacionalmente diferentes:

- baixa capacidade de preencher  → confiança baixa, readiness manual_review
- incompatibilidade real         → readiness bloqueada, com código do motivo
- impossibilidade de avaliar     → confiança None, readiness indeterminada
"""
from dataclasses import dataclass, field
from enum import StrEnum


class StatusDescoberta(StrEnum):
    """Desfecho da tentativa de ler as perguntas do formulário."""

    SUCESSO = "success"
    VAGA_NAO_ENCONTRADA = "job_not_found"
    VAGA_ENCERRADA = "job_closed"
    FALHA_TEMPORARIA = "temporary_failure"
    RESPOSTA_INVALIDA = "invalid_response"


class Prontidao(StrEnum):
    """O que fazer com esta vaga."""

    #: Todos os campos obrigatórios são conhecidos e nada bloqueia.
    PRONTA = "pronta"
    #: Dá para preencher a maior parte, mas algo exige um humano.
    REVISAO_MANUAL = "manual_review"
    #: Existe impedimento concreto; automatizar produziria candidatura inválida.
    BLOQUEADA = "bloqueada"
    #: Não foi possível ler o formulário. Não é o mesmo que "não dá para preencher".
    INDETERMINADA = "indeterminada"


class CodigoBloqueio(StrEnum):
    """Por que a automação não deve seguir. Códigos distintos porque as ações
    também são distintas: CPF ausente se resolve na configuração; incompatibilidade
    de work authorization é inelegibilidade; falha de leitura é para retentar."""

    CPF_AUSENTE = "cpf_ausente"
    WORK_AUTHORIZATION = "work_authorization_incompativel"
    PERGUNTA_DESCONHECIDA = "pergunta_obrigatoria_desconhecida"
    TIPO_NAO_SUPORTADO = "tipo_de_campo_nao_suportado"
    DESCOBERTA_INDISPONIVEL = "job_questions_unavailable"
    VAGA_ENCERRADA = "vaga_encerrada"


#: Motivo de indeterminação por status de descoberta.
MOTIVO_POR_STATUS = {
    StatusDescoberta.VAGA_NAO_ENCONTRADA: CodigoBloqueio.DESCOBERTA_INDISPONIVEL,
    StatusDescoberta.VAGA_ENCERRADA: CodigoBloqueio.VAGA_ENCERRADA,
    StatusDescoberta.FALHA_TEMPORARIA: CodigoBloqueio.DESCOBERTA_INDISPONIVEL,
    StatusDescoberta.RESPOSTA_INVALIDA: CodigoBloqueio.DESCOBERTA_INDISPONIVEL,
}

#: Falhas que valem retentar mais tarde — a vaga pode voltar a responder.
STATUS_RETENTAVEIS = frozenset({
    StatusDescoberta.FALHA_TEMPORARIA,
    StatusDescoberta.RESPOSTA_INVALIDA,
})


@dataclass(frozen=True)
class Pergunta:
    """Uma pergunta do formulário, já normalizada da resposta da plataforma."""

    label: str
    tipo: str
    obrigatoria: bool
    opcoes: list[dict] = field(default_factory=list)
    nome_campo: str = ""


@dataclass(frozen=True)
class Descoberta:
    """Resultado explícito da leitura do formulário.

    Nunca devolva só a lista: o chamador precisa do status para decidir se o
    silêncio significa "formulário simples" ou "não consegui ler".
    """

    status: StatusDescoberta
    perguntas: list[Pergunta] = field(default_factory=list)
    http_status: int | None = None
    detalhe: str = ""

    @property
    def ok(self) -> bool:
        return self.status is StatusDescoberta.SUCESSO

    @property
    def retentavel(self) -> bool:
        return self.status in STATUS_RETENTAVEIS


@dataclass(frozen=True)
class Bloqueio:
    codigo: CodigoBloqueio
    detalhe: str = ""

    def para_json(self) -> dict:
        return {"codigo": str(self.codigo), "detalhe": self.detalhe}


def montar_avaliacao(
    plataforma: str,
    descoberta: Descoberta,
    obrigatorias_conhecidas: list[str] | None = None,
    obrigatorias_desconhecidas: list[str] | None = None,
    opcionais_conhecidas: list[str] | None = None,
    opcionais_desconhecidas: list[str] | None = None,
    bloqueios: list[Bloqueio] | None = None,
) -> dict:
    """Consolida a avaliação de preenchimento no formato que vai para o banco.

    Regra dura: sem descoberta bem-sucedida não há confiança. `None`, não zero.
    """
    obr_ok = list(obrigatorias_conhecidas or [])
    obr_nok = list(obrigatorias_desconhecidas or [])
    opc_ok = list(opcionais_conhecidas or [])
    opc_nok = list(opcionais_desconhecidas or [])
    bloqueios = list(bloqueios or [])

    base = {
        "plataforma": plataforma,
        "discovery_status": str(descoberta.status),
        "http_status": descoberta.http_status,
        "known_required": len(obr_ok),
        "unknown_required": len(obr_nok),
        "known_optional": len(opc_ok),
        "unknown_optional": len(opc_nok),
        "manual_questions": obr_nok + opc_nok,
        "blockers": [b.para_json() for b in bloqueios],
    }

    if not descoberta.ok:
        codigo = MOTIVO_POR_STATUS.get(
            descoberta.status, CodigoBloqueio.DESCOBERTA_INDISPONIVEL
        )
        return {
            **base,
            "application_confidence": None,
            "required_coverage": None,
            "optional_coverage": None,
            "automation_eligible": False,
            "application_readiness": str(Prontidao.INDETERMINADA),
            "blocking_reason": str(codigo),
            "retentavel": descoberta.retentavel,
            "detalhe": descoberta.detalhe,
        }

    if bloqueios:
        return {
            **base,
            # Bloqueio conhecido é medição válida: sabemos que não dá.
            "application_confidence": 0.0,
            "required_coverage": None,
            "optional_coverage": None,
            "automation_eligible": False,
            "application_readiness": str(Prontidao.BLOQUEADA),
            "blocking_reason": str(bloqueios[0].codigo),
            "retentavel": False,
            "detalhe": bloqueios[0].detalhe,
        }

    total_obr = len(obr_ok) + len(obr_nok)
    total_opc = len(opc_ok) + len(opc_nok)
    cobertura_obr = 1.0 if total_obr == 0 else len(obr_ok) / total_obr
    cobertura_opc = 1.0 if total_opc == 0 else len(opc_ok) / total_opc

    # Duas faixas separadas, não uma média ponderada. Uma média deixava a
    # cobertura de opcionais compensar uma obrigatória faltando: um formulário
    # com 9/10 obrigatórias e todas as opcionais pontuava 0.92, acima dos 0.80
    # de um formulário com TODAS as obrigatórias e nenhuma opcional — quando o
    # segundo é o único dos dois que pode ser submetido.
    #
    #   obrigatória desconhecida → teto 0.5, nunca elegível a automação
    #   todas conhecidas         → piso 0.8, sobe com a cobertura de opcionais
    if obr_nok:
        confianca = round(cobertura_obr * 0.5, 2)
        prontidao = Prontidao.REVISAO_MANUAL
    else:
        confianca = round(0.8 + 0.2 * cobertura_opc, 2)
        prontidao = Prontidao.PRONTA

    return {
        **base,
        "application_confidence": confianca,
        # Coberturas separadas para ninguém precisar reinterpretar o número
        # composto depois.
        "required_coverage": round(cobertura_obr, 2),
        "optional_coverage": round(cobertura_opc, 2),
        # O gate de automação é booleano e independente do número: nenhuma
        # aritmética pode torná-lo verdadeiro com obrigatória desconhecida.
        "automation_eligible": not obr_nok and not bloqueios,
        "application_readiness": str(prontidao),
        "blocking_reason": (
            str(CodigoBloqueio.PERGUNTA_DESCONHECIDA) if obr_nok else None
        ),
        "retentavel": False,
        "detalhe": "",
    }


def avaliacao_nao_suportada(plataforma: str, detalhe: str) -> dict:
    """Plataforma sem meio de inspecionar o formulário antes de submeter."""
    return montar_avaliacao(
        plataforma,
        Descoberta(
            status=StatusDescoberta.FALHA_TEMPORARIA,
            detalhe=detalhe,
        ),
    )
