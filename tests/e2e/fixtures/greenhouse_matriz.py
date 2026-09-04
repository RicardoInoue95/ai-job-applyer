"""Matriz de formulários do Greenhouse, em 20 cenários.

Fixtures como dados, não como arquivos soltos: cada cenário declara a resposta
HTTP que a API do Greenhouse devolveria e o que se espera da avaliação. Assim a
matriz é enumerável — um teste parametrizado percorre todos e um novo cenário é
uma entrada nesta lista.

Os payloads seguem o formato real de
``boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}?questions=true``.

Grupos, na ordem em que o risco cresce:

1. Fluxos suportados      — a automação deve conseguir preencher
2. Exigem intervenção     — a automação deve RECUSAR e explicar por quê
3. Falhas de leitura      — a avaliação deve ser indeterminada, não zero
"""
from dataclasses import dataclass, field
from typing import Any


def campo(nome: str, tipo: str = "input_text", valores: list | None = None) -> dict:
    return {"name": nome, "type": tipo, "values": valores or []}


def pergunta(label: str, nome: str, tipo: str = "input_text",
             obrigatoria: bool = True, valores: list | None = None) -> dict:
    return {
        "label": label,
        "required": obrigatoria,
        "fields": [campo(nome, tipo, valores)],
    }


#: Campos que todo formulário do Greenhouse tem. Não contam como perguntas.
PADRAO = [
    pergunta("First Name", "first_name"),
    pergunta("Last Name", "last_name"),
    pergunta("Email", "email"),
    pergunta("Resume", "resume", "input_file"),
]

NIVEIS_INGLES = [
    {"label": "Básico", "value": 1},
    {"label": "Intermediário", "value": 2},
    {"label": "Avançado", "value": 3},
    {"label": "Fluente", "value": 4},
]
SIM_NAO = [{"label": "Sim", "value": 1}, {"label": "Não", "value": 0}]
ESTADOS = [
    {"label": "São Paulo (SP)", "value": 35},
    {"label": "Rio de Janeiro (RJ)", "value": 33},
]


@dataclass(frozen=True)
class Cenario:
    """Um formulário representativo e o desfecho esperado."""

    id: str
    grupo: str
    descricao: str
    #: Corpo JSON que a API devolveria. None significa corpo não-JSON.
    corpo: Any = None
    http_status: int = 200
    #: Exceção que a chamada HTTP levantaria (timeout, DNS).
    excecao: Exception | None = None
    #: Desfecho esperado.
    discovery_status: str = "success"
    readiness: str = "pronta"
    #: None quando a confiança não pode ser medida.
    confianca_e_none: bool = False
    blocking_reason: str | None = None
    min_obrigatorias_desconhecidas: int = 0
    cpf_configurado: bool = True
    retentavel: bool = False


def _job(questions: list[dict], **extra) -> dict:
    return {"id": 1, "title": "Data Engineer", "questions": questions, **extra}


# ── Grupo 1: fluxos suportados ────────────────────────────────────────────────

SUPORTADOS = [
    Cenario(
        "01_minimo", "suportado",
        "Formulário mínimo: nenhuma pergunta além do padrão",
        corpo=_job([]),
    ),
    Cenario(
        "02_campos_pessoais", "suportado",
        "Só os campos pessoais básicos",
        corpo=_job(PADRAO),
    ),
    Cenario(
        "03_upload_curriculo", "suportado",
        "Upload de currículo obrigatório",
        corpo=_job([*PADRAO, pergunta("Resume/CV", "resume", "input_file")]),
    ),
    Cenario(
        "04_cover_letter_opcional", "suportado",
        "Cover letter opcional não impede o envio",
        corpo=_job([*PADRAO,
                    pergunta("Cover Letter", "cover_letter", "textarea", obrigatoria=False)]),
    ),
    Cenario(
        "05_cover_letter_obrigatoria", "suportado",
        "Cover letter obrigatória: o sistema sempre gera uma",
        corpo=_job([*PADRAO, pergunta("Cover Letter", "cover_letter", "textarea")]),
    ),
    Cenario(
        "06_dropdown_radio_checkbox", "suportado",
        "Select, radio e checkbox com opções conhecidas",
        corpo=_job([
            *PADRAO,
            pergunta("Nível de inglês", "question_1", "multi_value_single_select", valores=NIVEIS_INGLES),
            pergunta("Estado de residência", "question_2", "multi_value_single_select", valores=ESTADOS),
            pergunta("Disponibilidade para trabalho presencial em São Paulo",
                     "question_3", "yes_no", valores=SIM_NAO),
        ]),
    ),
    Cenario(
        "07_perguntas_conhecidas", "suportado",
        "Perguntas customizadas que o _auto_answer sabe responder",
        corpo=_job([
            *PADRAO,
            pergunta("CPF", "question_10"),
            pergunta("URL do LinkedIn", "question_11"),
            pergunta("Cargo atual", "question_12"),
            pergunta("Empresa atual", "question_13"),
        ]),
    ),
    Cenario(
        "08_consentimento", "suportado",
        "Consentimento de privacidade — responder Sim é a única opção viável",
        corpo=_job([
            *PADRAO,
            pergunta("Você autoriza o consentimento para análise do seu perfil?",
                     "question_20", "yes_no", valores=SIM_NAO),
        ]),
    ),
]


# ── Grupo 2: exigem intervenção humana ────────────────────────────────────────

INTERVENCAO = [
    Cenario(
        "09_pergunta_desconhecida", "intervencao",
        "Pergunta obrigatória fora do vocabulário do _auto_answer",
        corpo=_job([*PADRAO, pergunta("Descreva seu maior desafio técnico", "question_30", "textarea")]),
        readiness="manual_review",
        blocking_reason="pergunta_obrigatoria_desconhecida",
        min_obrigatorias_desconhecidas=1,
    ),
    Cenario(
        # Era "não há dado configurado para responder", e virou o contrário: a
        # faixa de `pretensao` no config responde. O cenário deixou de descrever
        # a realidade quando o `_auto_answer` passou a consultar `salario.py` em
        # vez de só `dados_pessoais.salario`, que está vazio.
        #
        # Pretensão é a pergunta obrigatória que mais bloqueava envio no acervo —
        # 17 ocorrências —, então o valor deste cenário agora é garantir que ela
        # NÃO volte a bloquear. O caminho de bloqueio segue coberto pelo 09.
        "10_pretensao_salarial", "suportado",
        "Pretensão salarial respondida pela faixa configurada em `pretensao`",
        corpo=_job([*PADRAO, pergunta("Qual sua pretensão salarial?", "question_31")]),
        readiness="pronta",
    ),
    Cenario(
        "11_cpf_ausente", "intervencao",
        "CPF exigido pelo formulário e ausente na configuração",
        corpo=_job([*PADRAO, pergunta("CPF", "question_32")]),
        cpf_configurado=False,
        readiness="bloqueada",
        blocking_reason="cpf_ausente",
    ),
    Cenario(
        "12_work_authorization", "intervencao",
        "Vaga exclusiva dos EUA: inelegibilidade, não campo desconhecido",
        corpo=_job([
            *PADRAO,
            pergunta("Are you legally authorized to work in the United States?",
                     "question_33", "yes_no", valores=SIM_NAO),
        ]),
        readiness="bloqueada",
        blocking_reason="work_authorization_incompativel",
    ),
    Cenario(
        "13_tipo_nao_suportado", "intervencao",
        "Campo de assinatura: preencher produziria candidatura inválida",
        corpo=_job([*PADRAO, pergunta("Assinatura digital", "question_34", "signature")]),
        readiness="bloqueada",
        blocking_reason="tipo_de_campo_nao_suportado",
    ),
]


# ── Grupo 3: falhas de leitura e de submissão ─────────────────────────────────

FALHAS_LEITURA = [
    Cenario(
        "14_job_404", "falha_leitura",
        "Vaga não existe mais: leitura impossível, não formulário vazio",
        http_status=404, corpo={"error": "not found"},
        discovery_status="job_not_found",
        readiness="indeterminada", confianca_e_none=True,
        blocking_reason="job_questions_unavailable",
    ),
    Cenario(
        "15_http_500", "falha_leitura",
        "Servidor indisponível: falha temporária, vale retentar",
        http_status=503, corpo={"error": "unavailable"},
        discovery_status="temporary_failure",
        readiness="indeterminada", confianca_e_none=True,
        blocking_reason="job_questions_unavailable",
        retentavel=True,
    ),
    Cenario(
        "16_resposta_invalida", "falha_leitura",
        "HTTP 200 com corpo que não é JSON",
        corpo="<html>manutenção</html>",
        discovery_status="invalid_response",
        readiness="indeterminada", confianca_e_none=True,
        blocking_reason="job_questions_unavailable",
        retentavel=True,
    ),
    Cenario(
        "16b_json_sem_questions", "falha_leitura",
        "JSON válido mas sem a lista 'questions'",
        corpo={"id": 1, "title": "Data Engineer"},
        discovery_status="invalid_response",
        readiness="indeterminada", confianca_e_none=True,
        blocking_reason="job_questions_unavailable",
        retentavel=True,
    ),
    Cenario(
        "17_vaga_encerrada", "falha_leitura",
        "Vaga fechada continua acessível na API e pareceria formulário simples",
        corpo=_job([], closed_at="2026-08-01T00:00:00Z"),
        discovery_status="job_closed",
        readiness="indeterminada", confianca_e_none=True,
        blocking_reason="vaga_encerrada",
    ),
    Cenario(
        "17b_timeout", "falha_leitura",
        "Timeout de rede",
        excecao=TimeoutError("read timeout"),
        discovery_status="temporary_failure",
        readiness="indeterminada", confianca_e_none=True,
        blocking_reason="job_questions_unavailable",
        retentavel=True,
    ),
]


TODOS: list[Cenario] = [*SUPORTADOS, *INTERVENCAO, *FALHAS_LEITURA]


# ── Grupo 3b: desfechos de submissão ──────────────────────────────────────────
# Estes não passam pela descoberta: exercitam `avaliar_confirmacao`, que decide
# se a candidatura pode ser marcada como enviada.

@dataclass(frozen=True)
class CenarioSubmissao:
    id: str
    descricao: str
    sinais_fortes: dict = field(default_factory=dict)
    sinais_fracos: dict = field(default_factory=dict)
    perguntas_manuais: list = field(default_factory=list)
    status_esperado: str = "enviada_confirmada"


SUBMISSAO = [
    CenarioSubmissao(
        "18_confirmacao_inequivoca",
        "Redirecionamento para URL de confirmação do Greenhouse",
        sinais_fortes={"url de confirmação": True},
        status_esperado="enviada_confirmada",
    ),
    CenarioSubmissao(
        "19_resposta_ambigua",
        "Botão clicado, página diz 'obrigado', sem URL de confirmação",
        sinais_fortes={"url de confirmação": False},
        sinais_fracos={"texto de agradecimento": True},
        status_esperado="revisao_manual",
    ),
    CenarioSubmissao(
        "20_erro_de_validacao",
        "Formulário recusado: nenhum sinal de submissão",
        sinais_fortes={},
        sinais_fracos={},
        status_esperado="falha_automacao",
    ),
    CenarioSubmissao(
        "20b_confirmado_com_pergunta_pendente",
        "Aceito, mas com campo em branco — ainda pede conferência",
        sinais_fortes={"url de confirmação": True},
        perguntas_manuais=["Pretensão salarial"],
        status_esperado="revisao_manual",
    ),
]
