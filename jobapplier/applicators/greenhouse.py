"""Módulo 13 — Candidatura via Greenhouse usando Playwright (form submission real)."""
import logging
import re
from pathlib import Path

import requests

from jobapplier import salario
from jobapplier.applicators.base import (
    ENVIADA_CONFIRMADA,
    FALHA_AUTOMACAO,
    REVISAO_MANUAL,
    avaliar_confirmacao,
    capturar_falha,
    resultado,
)
from jobapplier.applicators.descoberta import (
    Bloqueio,
    CodigoBloqueio,
    Descoberta,
    Pergunta,
    StatusDescoberta,
    montar_avaliacao,
)
from jobapplier.applicators.identidade import resolver as resolver_identidade

logger = logging.getLogger(__name__)

#: Tipos de campo que a automação não sabe preencher com segurança. Encontrar um
#: deles é bloqueio, não "campo desconhecido": tentar preencher produziria uma
#: candidatura inválida em vez de uma incompleta.
TIPOS_NAO_SUPORTADOS = frozenset({"input_file_multiple", "signature", "captcha"})

API_BASE = "https://boards-api.greenhouse.io/v1/boards"
BOARD_BASE = "https://boards.greenhouse.io"

CAMPOS_PADRAO = {"first_name", "last_name", "preferred_name", "email", "phone",
                 "resume", "cover_letter", "resume_text", "cover_letter_text"}


# _parse_link e _DOMAIN_SLUG_MAP foram removidos: a resolução de identidade
# vive em jobapplier/applicators/identidade.py. Eles falhavam em 22% do
# acervo por tomar o subdomínio pelo domínio e por depender de um mapa fixo,
# e manter dois parsers seria outra fonte dupla de verdade.


def descobrir_perguntas(slug: str, job_id: str) -> Descoberta:
    """Lê as perguntas do formulário e classifica o desfecho.

    Devolve status explícito em vez de lista: 404 (vaga sumiu), 5xx (falha
    temporária, vale retentar), corpo ilegível e vaga encerrada levam a decisões
    operacionais diferentes, e antes todos viravam a mesma lista vazia — que era
    indistinguível de "formulário sem perguntas customizadas".
    """
    try:
        resp = requests.get(
            f"{API_BASE}/{slug}/jobs/{job_id}",
            params={"questions": "true"},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except Exception as exc:
        logger.warning("Falha de rede ao ler %s/%s: %s", slug, job_id, exc)
        return Descoberta(StatusDescoberta.FALHA_TEMPORARIA, detalhe=f"erro de rede: {exc}")

    if resp.status_code == 404:
        return Descoberta(
            StatusDescoberta.VAGA_NAO_ENCONTRADA, http_status=404,
            detalhe="vaga não existe mais no board",
        )
    if resp.status_code >= 500:
        return Descoberta(
            StatusDescoberta.FALHA_TEMPORARIA, http_status=resp.status_code,
            detalhe="servidor do Greenhouse indisponível",
        )
    if resp.status_code != 200:
        return Descoberta(
            StatusDescoberta.RESPOSTA_INVALIDA, http_status=resp.status_code,
            detalhe=f"HTTP inesperado {resp.status_code}",
        )

    try:
        dados = resp.json()
    except Exception as exc:
        return Descoberta(
            StatusDescoberta.RESPOSTA_INVALIDA, http_status=200,
            detalhe=f"corpo não é JSON: {exc}",
        )

    if not isinstance(dados, dict):
        return Descoberta(
            StatusDescoberta.RESPOSTA_INVALIDA, http_status=200,
            detalhe=f"JSON de tipo inesperado: {type(dados).__name__}",
        )

    # O Greenhouse mantém a vaga acessível depois de fechada. Sem esta checagem,
    # vaga encerrada pareceria formulário simples e ganharia confiança alta.
    if dados.get("closed_at") or dados.get("status") == "closed":
        return Descoberta(
            StatusDescoberta.VAGA_ENCERRADA, http_status=200,
            detalhe="vaga marcada como encerrada",
        )

    brutas = dados.get("questions")
    if not isinstance(brutas, list):
        return Descoberta(
            StatusDescoberta.RESPOSTA_INVALIDA, http_status=200,
            detalhe="resposta sem a lista 'questions'",
        )

    return Descoberta(
        StatusDescoberta.SUCESSO, http_status=200,
        perguntas=[p for p in map(_para_pergunta, brutas) if p is not None],
    )


def _para_pergunta(bruta) -> Pergunta | None:
    """Converte uma pergunta da API para o formato interno. None se inutilizável."""
    if not isinstance(bruta, dict):
        return None
    label = (bruta.get("label") or "").strip()
    if not label:
        return None

    campos = bruta.get("fields") or [{}]
    primeiro = campos[0] if campos and isinstance(campos[0], dict) else {}
    return Pergunta(
        label=label,
        tipo=(primeiro.get("type") or "").strip(),
        obrigatoria=bool(bruta.get("required")),
        opcoes=primeiro.get("values") or [],
        nome_campo=(primeiro.get("name") or "").strip(),
    )


def _get_job_questions(slug: str, job_id: str) -> list[dict]:
    try:
        resp = requests.get(
            f"{API_BASE}/{slug}/jobs/{job_id}",
            params={"questions": "true"},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            return resp.json().get("questions", [])
    except Exception as exc:
        logger.warning("Não foi possível buscar perguntas: %s", exc)
    return []


def _is_yes_no(field_type: str, values: list) -> bool:
    if field_type in ("yes_no", "boolean"):
        return True
    if field_type == "multi_value_single_select":
        labels = {v.get("label", "").lower() for v in values}
        return bool({"yes", "no"} & labels or {"sim", "não"} & labels)
    return False


def _yes_value(values: list) -> str:
    return (_pick_value(values, "Yes") or _pick_value(values, "Sim")
            or _pick_value(values, "yes") or "yes")


def _no_value(values: list) -> str:
    return (_pick_value(values, "No") or _pick_value(values, "Não")
            or _pick_value(values, "no") or "no")


def _pick_value(values: list, label_hint: str) -> str | None:
    if not label_hint:
        return None
    hint_lower = label_hint.lower()
    for v in values:
        if hint_lower in v.get("label", "").lower():
            return str(v.get("value", ""))
    return None


def _value_to_label(values: list, value_id: str) -> str | None:
    """Converte ID numérico do Greenhouse de volta para o label de exibição."""
    for v in values:
        if str(v.get("value", "")) == str(value_id):
            return v.get("label", "")
    return None


#: Texto que a página mostra quando exige um humano para submeter. Vindo de
#: captura real do formulário da Adyen: "A verification code was sent to
#: <e-mail>. To submit your application, enter the 8-character code to confirm
#: you're a human."
_MARCAS_VERIFICACAO = (
    "verification code was sent",
    "confirm you're a human",
    "confirm you are a human",
    "enter the 8-character code",
    "código de verificação",
    "codigo de verificacao",
    "confirme que você é humano",
)

#: Campos que só existem nessa etapa. Confirmam o texto: página que fala em
#: "verification code" num aviso de privacidade não tem onde digitar um.
#:
#: Os dois primeiros vêm do HTML real da Adyen, capturado em
#: `data/screenshots/falhas/`: são oito caixas de um caractere,
#: `id="security-input-0"` até `-7`, **sem atributo `name`**. A primeira versão
#: destes seletores procurava `name*='security_code'` e não casava com nada — o
#: texto era detectado, o campo não, e a checagem exige os dois, então a Adyen
#: continuava caindo em "falha técnica".
_SELETORES_VERIFICACAO = (
    "input[id^='security-input']",
    "input[aria-errormessage*='verification' i]",
    "input[autocomplete='one-time-code']",
    "input[name*='security_code' i]",
    "input[name*='verification' i]",
    "input[id*='security_code' i]",
)


def _pede_verificacao_humana(page, content: str) -> bool:
    """A página está pedindo prova de que há um humano submetendo?

    Exige texto **e** campo. Só o texto daria falso positivo em qualquer página
    que mencione verificação numa política de privacidade, e falso positivo aqui
    é caro: a vaga entraria em `STATUS_BLOQUEIA_RETENTATIVA` e nunca mais seria
    tentada sozinha.
    """
    if not any(m in content for m in _MARCAS_VERIFICACAO):
        return False
    for seletor in _SELETORES_VERIFICACAO:
        try:
            if page.query_selector(seletor) is not None:
                return True
        except Exception:
            continue
    return False


def _is_diversidade(label: str) -> bool:
    label_lower = label.lower()
    return any(d in label_lower for d in [
        "gênero", "genero", "orientação sexual", "orientacao sexual",
        "raça", "raca", "etnia", "deficiência", "deficiencia",
    ])


def _auto_answer(
    label: str, field_type: str, values: list,
    resume: dict, normalizado: dict, config_dados: dict | None = None,
) -> str | list | None:
    config_dados = config_dados or {}
    label_lower = label.lower()

    # ── Veto central, antes de qualquer regra ────────────────────────────────
    # A política de resposta vive em `agents/respostas.py`, com testes, e não
    # tinha nenhum chamador — segurança que não roda. Aplicá-la aqui é o que a
    # torna real, e o formato é veto e não reescrita: as ~40 regras abaixo
    # continuam decidindo o valor, mas nenhuma delas pode devolver algo que a
    # política proíbe.
    #
    # Antes cada ramo precisava lembrar sozinho de recusar dado sensível, e o
    # esquecimento não fazia barulho: "Consentimento - Diversidade e Inclusão"
    # caía no sim automático de consentimento porque a regra de consentimento
    # não sabia de diversidade.
    from jobapplier.agents import respostas

    classe = respostas.classificar(label)
    if classe is respostas.Classe.SENSIVEL:
        # Pergunta sensível não passa por NENHUMA das regras abaixo — era esse o
        # ponto do veto, e ele continua. O que muda é o destino: em vez de sempre
        # `None`, vai para a autodeclaração, que devolve `None` enquanto o
        # candidato não tiver declarado o valor.
        #
        # Repetir a declaração dele não é o sistema decidindo por ele — é a mesma
        # lógica do banco de respostas. Antes, o ramo de diversidade lá embaixo
        # era inalcançável: código morto lendo uma config que nunca era usada, e
        # raça e gênero viravam pergunta manual em todo formulário.
        return _autodeclaracao(label_lower, values, config_dados)

    # Pergunta composta pede que TODAS as partes sejam verdadeiras. "Experiência
    # com Spark e Kafka" com só uma das duas é "não" — e como não dá para saber
    # qual parte o candidato cobre sem lê-la, a resposta é dele.
    #
    # Consentimento fica de fora: ali o "e" é gramatical, não são duas condições
    # sobre o candidato. "Dados confidenciais E manuseados conforme a Política de
    # Privacidade" é um consentimento só, e o veto o transformava em pergunta
    # manual — travando toda candidatura do c6bank depois do resto ter dado certo.
    if (classe is not respostas.Classe.CONSENTIMENTO
            and respostas._e_composta(label) and _is_yes_no(field_type, values)):
        return None
    techs_resume = [t.lower() for t in resume.get("tecnologias", [])]
    experiencias = resume.get("experiencias", [])
    cargo_atual = experiencias[0].get("cargo", "") if experiencias else ""
    empresa_atual = experiencias[0].get("empresa", "") if experiencias else ""

    # ── Identificação básica, por rótulo ─────────────────────────────────────
    # No Greenhouse estes são preenchidos por seletor fixo (`#first_name`,
    # `#email`) e nunca passavam por aqui. A extensão de navegador é o primeiro
    # chamador que os manda por rótulo — e nome, e-mail e telefone são os três
    # campos mais comuns de qualquer formulário. Ficavam como pergunta manual.
    if any(k in label_lower for k in ("nome completo", "full name", "seu nome",
                                      "your name")) or label_lower.strip() in (
                                          "nome", "name"):
        return resume.get("nome") or None

    # Antes de "primeiro nome": "Nome de preferência" contém "nome" e casaria com
    # a regra errada. É campo OBRIGATÓRIO em vários formulários Greenhouse e não
    # era preenchido — a candidatura do c6bank parou com "Nome de preferência é
    # obrigatório" depois de todo o resto ter dado certo.
    if any(k in label_lower for k in ("nome de preferência", "nome de preferencia",
                                      "preferred name", "nome social",
                                      "como prefere ser chamad")):
        nome = resume.get("nome") or ""
        return nome.split()[0] if nome else None

    if any(k in label_lower for k in ("primeiro nome", "first name")):
        nome = resume.get("nome") or ""
        return nome.split()[0] if nome else None

    if any(k in label_lower for k in ("sobrenome", "last name", "surname")):
        partes = (resume.get("nome") or "").split()
        return " ".join(partes[1:]) if len(partes) > 1 else None

    if any(k in label_lower for k in ("e-mail", "email", "correio")):
        return resume.get("email") or None

    if any(k in label_lower for k in ("telefone", "celular", "phone", "whatsapp")):
        return resume.get("telefone") or None

    if "cpf" in label_lower:
        return config_dados.get("cpf") or None

    # Documentos que a Gupy pede na etapa de perguntas da empresa. Sem eles no
    # `dados_pessoais` o retorno é None e a pergunta vira manual — que é o
    # correto: não se inventa um RG (invariante 3).
    #
    # `\brg\b` e não `"rg" in label`: "Órgão" contém "rg", e casar por substring
    # devolveria o número do RG para a pergunta do órgão emissor. A do órgão é
    # testada antes por conter os dois termos.
    tem_rg = bool(re.search(r"\brg\b", label_lower)) or "registro geral" in label_lower
    if tem_rg and any(k in label_lower for k in ("emiss", "expedi", "org")):
        return config_dados.get("rg_orgao_emissor") or None
    if tem_rg:
        return config_dados.get("rg") or None

    if "nome da mãe" in label_lower or "nome da mae" in label_lower:
        return config_dados.get("nome_mae") or None

    if "nome do pai" in label_lower:
        return config_dados.get("nome_pai") or None

    if "naturalidade" in label_lower:
        return config_dados.get("naturalidade") or None

    if "linkedin" in label_lower:
        return resume.get("linkedin") or None

    if "github" in label_lower:
        return resume.get("github") or None

    if any(k in label_lower for k in ["cargo atual", "current position", "current role", "seu cargo"]):
        return cargo_atual or None

    if any(k in label_lower for k in [
        "empresa atual", "current company", "nome da empresa",
        "empresa em que", "empresa que você trabalha", "last company",
        "most recent company", "current or most recent", "current employer",
    ]):
        return empresa_atual or None

    # Estado de residência
    if any(k in label_lower for k in ["estado", "estado de resid"]):
        loc = resume.get("localizacao", "").lower()
        if "são paulo" in loc or "sp" in loc:
            return _pick_value(values, "São Paulo (SP)") or _pick_value(values, "São Paulo")
        return None

    # País de residência. Vem ANTES da cidade de propósito: a regra da cidade
    # casa a substring "reside", que engole "country where you currently reside"
    # e devolve None — o país virava pergunta manual por acidente de ordem, em
    # todo board internacional.
    if any(k in label_lower for k in [
        "country where you currently reside", "country of residence",
        "country you reside", "país de residência", "pais de residencia",
        "país onde reside", "pais onde reside",
    ]):
        if field_type in ("input_text", "textarea"):
            return "Brazil"
        return _pick_value(values, "Brazil") or _pick_value(values, "Brasil")

    # Cidade de residência
    #
    # `\bcidade\b` e não `"cidade" in`: **"privacidade" termina em "cidade"**, e
    # "Você está de acordo com a Política de Privacidade?" caía aqui, não achava
    # São Paulo na lista e devolvia None. Todo formulário brasileiro tem essa
    # frase, então todo consentimento virava pergunta manual — e a candidatura
    # parava depois de tudo o mais ter dado certo. Segundo caso hoje de termo
    # curto casando por substring; o primeiro foi "rg" dentro de "órgão".
    if (re.search(r"\bcidade\b", label_lower)
            or any(k in label_lower for k in ["reside", "onde você mora"])):
        # Campo de texto: escreve a localização direto. A regra abaixo só sabia
        # escolher opção numa lista, então "Cidade onde reside" em campo aberto
        # caía fora e virava pergunta manual — invisível enquanto só o
        # Greenhouse chamava, porque lá o campo é `#candidate-location`.
        if field_type in ("input_text", "textarea"):
            return resume.get("localizacao") or None
        loc = resume.get("localizacao", "").lower()
        if "são paulo" in loc:
            # Duas passadas, exato antes de prefixo. Uma passada única aceitando
            # ambos deixava a ordem da lista decidir: um "São Paulo - Zona Sul"
            # listado antes do "São Paulo" simples ganhava, respondendo um
            # bairro que o currículo não informa.
            exatos = {"são paulo", "sao paulo", "são paulo (sp)", "sao paulo (sp)"}
            for v in values:
                if v.get("label", "").strip().lower() in exatos:
                    return str(v.get("value", ""))
            for v in values:
                if v.get("label", "").strip().lower().startswith(("são paulo", "sao paulo")):
                    return str(v.get("value", ""))
        return None

    if any(k in label_lower for k in ["disponibilidade", "presencial", "híbrido", "hibrido", "são paulo", "sao paulo"]):
        loc_candidato = resume.get("localizacao", "").lower()
        in_sp = "são paulo" in loc_candidato or ", sp" in loc_candidato
        if _is_yes_no(field_type, values):
            return _yes_value(values) if in_sp else _no_value(values)

    if any(k in label_lower for k in ["inglês", "ingles", "english", "fluência", "fluencia", "língua inglesa"]):
        idiomas = resume.get("idiomas", [])
        entrada_ingles = next(
            (i for i in idiomas
             if "inglês" in (i.get("nome") or "").lower()
             or "english" in (i.get("nome") or "").lower()),
            None,
        )

        # Campo Sim/Não é resolvido ANTES do mapeamento de nível. Quando a
        # verificação vinha depois do loop, um currículo com inglês devolvia
        # "Avançado" para um campo Sim/Não — valor que não casa com nenhuma
        # opção, deixando o campo em branco. E sem inglês no currículo o código
        # respondia "Sim", o que é afirmar algo que o currículo não sustenta.
        if _is_yes_no(field_type, values):
            return _yes_value(values) if entrada_ingles else _no_value(values)

        if entrada_ingles:
            nivel = (entrada_ingles.get("nivel") or "").lower()
            nivel_map = {
                "básico": "Básico", "intermediário": "Intermediário",
                "avançado": "Avançado", "fluente": "Fluente", "nativo": "Nativo",
            }
            for k, v in nivel_map.items():
                if k in nivel:
                    return _pick_value(values, v) or v
            return _pick_value(values, "Intermediário") or "Intermediário"

        return _pick_value(values, "Intermediário")

    if any(k in label_lower for k in ["etl", "elt", "pipeline de dados"]):
        has_etl = any(
            s in t for s in ["etl", "elt", "pipeline", "airflow", "dagster", "dbt"]
            for t in techs_resume
        )
        if _is_yes_no(field_type, values):
            return _yes_value(values) if has_etl else _no_value(values)
        if field_type == "input_text" and has_etl:
            etl_tools = [t for t in resume.get("tecnologias", []) if any(
                s in t.lower() for s in ["etl", "elt", "pipeline", "airflow", "dbt", "factory", "databricks"]
            )]
            return f"Sim. Ferramentas: {', '.join(etl_tools[:4])}" if etl_tools else "Sim"

    if any(k in label_lower for k in ["cloud", "nuvem", "cloud computing"]):
        has_cloud = any(
            s in t for s in ["cloud", "aws", "azure", "gcp", "databricks", "snowflake"]
            for t in techs_resume
        )
        if _is_yes_no(field_type, values):
            return _yes_value(values) if has_cloud else _no_value(values)

    if any(k in label_lower for k in ["financeiro", "bancário", "bancario", "financial", "setor financ"]):
        desc_exp = " ".join(e.get("descricao", "") for e in experiencias).lower()
        has_fin = any(k in desc_exp for k in ["financeiro", "banco", "fintech", "bci", "b3", "fundo"])
        if _is_yes_no(field_type, values):
            return _yes_value(values) if has_fin else _no_value(values)

    if any(k in label_lower for k in ["em qual área", "área atuou", "area atuou", "qual área atuou"]):
        for preference in ["Engenharia de Dados", "Arquitetura de Dados", "Data Science", "Nenhuma das listadas"]:
            val = _pick_value(values, preference)
            if val:
                return val

    if field_type == "multi_value_multi_select":
        if any(k in label_lower for k in ["linguagem", "ferramenta", "tecnologia", "conhecimento", "norma"]):
            matched = []
            for v in values:
                v_label = v.get("label", "").lower()
                v_id = str(v.get("value", ""))
                # Para labels muito curtos (≤2 chars como "R", ".go"), exige match exato
                if len(v_label) <= 2:
                    if v_label in techs_resume:
                        matched.append(v_id)
                    continue
                # Match direto (substring bidirecional, mínimo 3 chars)
                if any((t in v_label or v_label in t) and len(min(t, v_label, key=len)) >= 3
                       for t in techs_resume):
                    matched.append(v_id)
                    continue
                # Sinônimos agrupados
                if any(k in v_label for k in ["big data", "spark", "hadoop", "databricks"]):
                    if any(s in t for s in ["spark", "databricks", "hadoop", "pyspark"] for t in techs_resume):
                        matched.append(v_id)
                        continue
                if "power bi" in v_label or "tableau" in v_label or "looker" in v_label:
                    if any(s in t for s in ["power bi", "tableau", "looker"] for t in techs_resume):
                        matched.append(v_id)
                        continue
                if any(k in v_label for k in ["kafka", "rabbitmq", "mensageria"]):
                    if any(s in t for s in ["kafka", "rabbitmq"] for t in techs_resume):
                        matched.append(v_id)
                        continue
            return matched if matched else None

    tech_keywords_map = {
        "sql": ["sql"],
        "python": ["python"],
        "spark": ["spark", "pyspark"],
        "ci/cd": ["ci/cd", "cicd", "devops"],
        "dbt": ["dbt"],
        "airflow": ["airflow"],
        "kafka": ["kafka"],
        "power bi": ["power bi", "powerbi"],
        "looker": ["looker"],
        "tableau": ["tableau"],
    }
    if _is_yes_no(field_type, values):
        for key, syns in tech_keywords_map.items():
            if any(s in label_lower for s in syns):
                if key == "ci/cd":
                    cicd_syns = [*syns, "iac", "terraform", "jenkins", "github actions", "gitlab"]
                    has_tech = any(s in t for s in cicd_syns for t in techs_resume)
                else:
                    has_tech = any(s in t for s in syns for t in techs_resume)
                return _yes_value(values) if has_tech else _no_value(values)

    if any(k in label_lower for k in ["senioridade", "seniority", "nível profissional", "nivel profissional"]):
        return (_pick_value(values, "Pleno") or _pick_value(values, "Mid")
                or _pick_value(values, "Intermediário"))

    if any(k in label_lower for k in ["tempo de experiência", "anos de experiência", "experiência profissional"]):
        return (_pick_value(values, "1 a 2 anos") or _pick_value(values, "2 a 3 anos")
                or _pick_value(values, "1 a 3 anos") or _pick_value(values, "2 anos"))

    if "agente" in label_lower and "autônom" in label_lower and _is_yes_no(field_type, values):
        return _no_value(values)

    if any(k in label_lower for k in [
        "consentimento", "consent", "análise do seu perfil", "analise do seu perfil",
        "otimizar a análise",
        # A regra de privacidade mais abaixo só conhece inglês ("privacy
        # policy", "privacy notice"), e todo formulário brasileiro escreve
        # "Política de Privacidade". Entram AQUI, e não lá, porque este ramo tem
        # a guarda que recusa consentir em dado sensível.
        "política de privacidade", "politica de privacidade",
        "tratamento de dados", "proteção de dados", "protecao de dados", "lgpd",
        "de acordo em fornecer",
    ]):
        # Consentir em processar a candidatura é formalidade sem a qual nada
        # anda. Consentir em fornecer raça, gênero ou deficiência é outra coisa:
        # é a categoria que a regra de nunca-inferir protege, e dizer "sim" por
        # ele entrega o dado que ele talvez não quisesse dar.
        # "Consentimento - Diversidade e Inclusão (D&I)" caía no sim automático.
        if _is_diversidade(label) or any(
            k in label_lower for k in ("diversidade", "d&i", "inclusão", "inclusao",
                                       "dados sensíveis", "dados sensiveis")):
            return None
        if _is_yes_no(field_type, values):
            return _yes_value(values)

    # Acknowledge / privacy / data protection / AI policy
    if any(k in label_lower for k in [
        "acknowledge", "applicant privacy", "data protection", "point of data transfer",
        "responsible use policy", "i confirm i have read", "privacy notice", "privacy policy",
        "please email me", "job alerts", "future job openings",
    ]):
        if _is_yes_no(field_type, values):
            return _yes_value(values)
        if field_type in ("input_text", "textarea"):
            return "Yes"
        if values:
            return _yes_value(values)

    # How did you hear about us
    if any(k in label_lower for k in [
        "how did you hear", "how did you find", "how did you learn", "how did you first learn",
        "source of hire", "source of application", "como ficou sabendo", "como você ficou",
        "canal", "canais",
        # Redação da Gupy, vista num formulário real: nenhuma das acima casava,
        # e a pergunta virava manual mesmo tendo resposta óbvia.
        "onde você encontrou", "onde voce encontrou", "como você conheceu",
        "como voce conheceu", "como soube desta", "onde viu esta vaga",
    ]):
        if field_type in ("input_text", "textarea"):
            return "LinkedIn"
        val = (_pick_value(values, "LinkedIn") or _pick_value(values, "Glassdoor")
               or _pick_value(values, "Job Board") or _pick_value(values, "Other"))
        if val:
            return [val] if field_type == "multi_value_multi_select" else val

    # Remuneração ATUAL não é pretensão. "What is your current compensation?" e
    # "Do you currently receive any variable compensation?" casavam com a palavra
    # "compensation" e passaram a receber a faixa desejada assim que a pretensão
    # virou automática — respondendo o que ele quer ganhar na pergunta sobre o
    # que ele ganha. Isso é declaração falsa sobre um fato, não ênfase, e o
    # currículo não informa salário atual. Pergunta manual.
    if any(k in label_lower for k in [
        "current compensation", "current salary", "currently receive",
        "present salary", "salário atual", "salario atual",
        "remuneração atual", "remuneracao atual", "último salário",
    ]):
        return None

    # Salary expectation
    if any(k in label_lower for k in [
        "salary expectation", "expected salary", "desired salary",
        "pretensão salarial", "pretensao salarial", "remuneração esperada",
        "remuneracao esperada", "salário desejado", "salario desejado",
        "salary range", "compensation expectation", "expected compensation",
    ]):
        # Sem valor configurado, NÃO responde. O fallback anterior escrevia
        # "A combinar" — não é mentira, mas é uma decisão de negociação tomada
        # em nome do usuário, que nunca a configurou. Alguns recrutadores
        # descartam "a combinar"; outros esperam um número. É preferência do
        # candidato, e preferência ausente vira pergunta manual.
        #
        # Configure em dados_pessoais.salario (ou salario_esperado no currículo)
        # para fixar um texto próprio — inclusive "A combinar", se for a sua
        # escolha. Sem isso, a faixa de `pretensao` na config responde.
        salary = config_dados.get("salario") or resume.get("salario_esperado")
        if salary:
            return str(salary) if field_type in ("input_text", "textarea") else None

        # A faixa vive em `pretensao` no config e o módulo já sabe converter para
        # PJ e formatar por tipo de campo. Antes esta função só olhava
        # `dados_pessoais.salario`, que está vazio: duas fontes de pretensão, e a
        # que o formulário consultava não era a que o usuário configurou.
        # "Pretensão salarial" é a pergunta obrigatória que mais bloqueia envio
        # no acervo — 17 ocorrências.
        if field_type not in ("input_text", "textarea", "number"):
            return None
        resposta = salario.responder(
            texto_vaga=" ".join(str(normalizado.get(c) or "") for c in
                                ("regime_contratacao", "cargo", "modalidade")),
            senioridade=str(normalizado.get("senioridade") or ""),
            tipo_campo="number" if field_type == "number" else "input_text",
        )
        return resposta["valor"] if resposta else None

    # Empregador e cargo atual/anterior. O currículo tem os dois; a variante
    # "current or previous" não casava com a regra de "cargo atual".
    if any(k in label_lower for k in [
        "current or previous employer", "current or most recent employer",
        "most recent employer", "empregador atual", "empresa atual",
    ]) and field_type in ("input_text", "textarea"):
        return empresa_atual or None

    if any(k in label_lower for k in [
        "current or previous job title", "current or most recent title",
        "most recent job title", "current title",
    ]) and field_type in ("input_text", "textarea"):
        return cargo_atual or None

    # City / location (text field)
    if any(k in label_lower for k in [
        "city of residence", "cidade de residência", "current location",
        "your location", "where are you located", "current city",
    ]) and field_type in ("input_text", "textarea"):
        return resume.get("localizacao", "São Paulo, Brasil")

    # Preferred name
    if "preferred name" in label_lower:
        nome = resume.get("nome", "")
        return nome.split()[0] if nome else None

    # Vínculo prévio com ESTA empresa. As variantes reais dos boards não casavam
    # com a lista antiga — "Have you ever been employed by Stripe", "Você já
    # trabalhou em algum momento no C6 Bank?", "Are you currently or have you
    # ever worked for Airbnb in any capacity?". É a segunda família que mais
    # bloqueia envio, com ~25 ocorrências no acervo.
    if any(k in label_lower for k in [
        "previously been employed", "previously worked for", "former employee",
        "worked here before", "have you worked at", "have you ever been employed",
        "have you ever worked", "ever worked for", "employed by",
        "já trabalhou", "ja trabalhou", "trabalhou conosco", "ex-funcionário",
        "ex-funcionario", "você trabalha", "voce trabalha",
    ]) and _is_yes_no(field_type, values):
        # "Não" aqui é derivação, não chute: o currículo lista o histórico
        # completo, então a ausência da empresa nele é informação. Se ela
        # aparecer, o sistema não responde — quem trabalhou lá sabe responder
        # melhor que uma comparação de strings.
        empregadores = " ".join(
            str(e.get("empresa") or "") for e in experiencias).lower()
        empresa_vaga = str(normalizado.get("empresa") or "").lower().strip()
        if empresa_vaga and empresa_vaga in empregadores:
            return None
        return _no_value(values)

    # Autorização de trabalho NO PAÍS DA VAGA. Respondia "Sim" sempre, e a
    # pergunta é sobre o país onde a vaga está — que na maioria dos boards do
    # Greenhouse não é o Brasil. "Sim" ali é declaração falsa numa pergunta
    # eliminatória, e o candidato só descobre na entrevista.
    if any(k in label_lower for k in [
        "authorized to work in the country", "authorised to work in the country",
        "right to work where this role",
    ]):
        pais_vaga = " ".join(str(normalizado.get(c) or "") for c in
                             ("pais", "localizacao", "modalidade")).lower()
        brasileira = any(t in pais_vaga for t in ("brasil", "brazil", " br"))
        if not brasileira:
            return None
        if _is_yes_no(field_type, values):
            return _yes_value(values)
        # "What is the source of your right to work?"
        val = (_pick_value(values, "National") or _pick_value(values, "Citizen")
               or _pick_value(values, "Permanent") or _pick_value(values, "Other"))
        return val

    # Willing to relocate
    if any(k in label_lower for k in ["willing to relocate", "disposto a se mudar", "open to relocation"]):
        if _is_yes_no(field_type, values):
            return _yes_value(values)

    # Hybrid / office attendance willingness
    if any(k in label_lower for k in ["willing to work from our office", "hybrid", "3 days per week"]):
        if _is_yes_no(field_type, values):
            return _yes_value(values)

    if any(k in label_lower for k in ["conhece alguém", "conhece algum", "conhece alguma", "já participou"]):
        if _is_yes_no(field_type, values):
            return _no_value(values)

    # ── Parentesco: a resposta muda com a empresa ────────────────────────────
    # "Não" é verdade em quase toda parte e falso onde ele tem parente. Responder
    # globalmente escreveria uma declaração falsa num formulário real — e é a
    # invariante 3 pelo caminho menos óbvio, o de uma resposta certa reaproveitada
    # onde não vale. Nas empresas declaradas, a resposta é dele.
    if any(k in label_lower for k in ("parentesco", "parente", "familiar",
                                      "grau de parentesco")):
        alvo = (normalizado.get("empresa") or "").lower()
        excecoes = [str(e).lower().strip()
                    for e in (config_dados.get("parentesco_empresas") or []) if e]
        if any(e and e in alvo for e in excecoes):
            return None
        if _is_yes_no(field_type, values):
            return _no_value(values)

    if any(k in label_lower for k in ("indicad", "indicou", "indicação de",
                                      "referral", "referred by")):
        if _is_yes_no(field_type, values):
            return _no_value(values)

    return None


def _autodeclaracao(label_lower: str, values: list, config_dados: dict) -> str | None:
    """Responde pergunta sensível **só** com o que o candidato declarou.

    Sem declaração, `None` — vira pergunta manual, nunca um chute. O valor é
    casado contra as opções do formulário: cada empresa escreve as suas de um
    jeito, e devolver o texto do config direto não marcaria nada.
    """
    d = config_dados.get("diversidade") or {}

    if any(k in label_lower for k in ("deficiência", "deficiencia", "pcd")):
        v = d.get("deficiencia", "")
        if not v:
            return None
        # "Não" precisa casar com "Não, não possuo deficiência", "No", "No (…)".
        if v.strip().lower().startswith(("não", "nao", "no")):
            return (_pick_value(values, "Não") or _pick_value(values, "Nao")
                    or _pick_value(values, "No"))
        return _pick_value(values, v)

    for termos, chave in (
        (("identidade de gênero", "identidade de genero", "gênero", "genero"), "genero"),
        (("orientação sexual", "orientacao sexual"), "orientacao"),
        (("raça", "raca", "etnia", "cor"), "raca"),
    ):
        if any(t in label_lower for t in termos):
            v = d.get(chave, "")
            return _pick_value(values, v) if v else None
    return None


# ── Playwright form filler ────────────────────────────────────────────────────

def _pw_fill_text(page, selector: str, text: str):
    """Preenche campo de texto, ignorando se não existir."""
    try:
        el = page.query_selector(selector)
        if el and el.is_visible():
            el.fill(text)
    except Exception as exc:
        logger.debug("fill %s: %s", selector, exc)


def _pw_marcar_checkbox(page, field_id: str, valor: str) -> bool:
    """Marca o checkbox de `field_id` cujo value é `valor`. False se não é checkbox.

    O Greenhouse monta o id do input concatenando o nome do campo e o value:
    ``question_67923270[]`` + ``_731111200``. Confere `is_checked()` depois de
    marcar em vez de assumir sucesso — o input real fica sob um SVG decorativo, e
    um clique interceptado falha sem levantar exceção.
    """
    try:
        cb = page.query_selector(f'input[type=checkbox][id="{field_id}_{valor}"]')

        # `_auto_answer` devolve 'yes' para consentimento, não o value numérico da
        # opção. O id exato então não existe. Quando o campo tem uma única caixa,
        # 'yes' só pode significar aquela caixa.
        if cb is None and str(valor).strip().lower() in _AFIRMATIVOS:
            caixas = page.query_selector_all(
                f'input[type=checkbox][id^="{field_id}_"]'
            )
            if len(caixas) == 1:
                cb = caixas[0]
            elif len(caixas) > 1:
                logger.warning(
                    "Campo %s tem %d caixas e a resposta é '%s': ambíguo, não marcado.",
                    field_id, len(caixas), valor,
                )
                return False

        if cb is None:
            return False
        if not cb.is_checked():
            cb.check(timeout=3000)
        marcado = cb.is_checked()
        if not marcado:
            logger.warning("Checkbox %s não aceitou a marcação.", field_id)
        return marcado
    except Exception as exc:
        logger.warning("Erro ao marcar checkbox %s: %s", field_id, exc)
        return False


#: Formas afirmativas que `_auto_answer` pode devolver para um consentimento.
_AFIRMATIVOS = frozenset({"yes", "sim", "true", "1", "y", "s"})

#: Níveis de idioma: o currículo é em português, os formulários costumam ser em
#: inglês. Sem isto, "Avançado" não casa com nenhuma opção e o campo fica vazio
#: com a resposta certa já calculada.
_NIVEIS_IDIOMA: dict[str, tuple[str, ...]] = {
    "nativo": ("native", "nativo", "fluent"),
    "fluente": ("fluent", "fluente", "native"),
    "avancado": ("advanced", "avançado", "avancado", "fluent"),
    "intermediario": ("intermediate", "intermediário", "intermediario"),
    "basico": ("beginner", "basic", "básico", "basico", "elementary"),
    "iniciante": ("beginner", "basic", "iniciante"),
}


def _equivalentes(texto: str) -> tuple[str, ...]:
    """Sinônimos aceitáveis para casar uma resposta com o rótulo de uma opção."""
    import unicodedata

    chave = "".join(
        c for c in unicodedata.normalize("NFD", texto.strip().lower())
        if unicodedata.category(c) != "Mn"
    )
    return _NIVEIS_IDIOMA.get(chave, ())


def _pw_select_react(page, field_id: str, label_text: str, timeout: int = 4000) -> bool:
    """Seleciona uma opção em um react-select dropdown."""
    bare_id = field_id.replace("[]", "")
    selector = f'[id="{field_id}"]'
    opt_selector = f'[id*="react-select-"][id*="{bare_id}"][id*="-option"]'
    try:
        # Candidatos em ordem de preferência: o rótulo pedido e, só depois, seus
        # equivalentes. "Avançado" precisa achar "C. Advanced" num formulário em
        # inglês, mas sem nunca preferir o equivalente ao termo exato.
        candidatos = (label_text.lower(), *_equivalentes(label_text))

        page.click(selector, timeout=3000)
        page.wait_for_selector(opt_selector, timeout=timeout)

        def escolher() -> bool:
            opcoes = [
                (o, (o.inner_text() or "").lower())
                for o in page.query_selector_all(opt_selector)
            ]
            for termo in candidatos:
                for opt, texto in opcoes:
                    if termo in texto:
                        opt.click()
                        return True
            return False

        if escolher():
            return True
        # Fallback: digitar para filtrar a lista.
        page.fill(selector, label_text[:20])
        page.wait_for_timeout(600)
        if escolher():
            return True
        logger.warning(
            "Nenhuma opção de '%s' casa com '%s'.", field_id, label_text[:40]
        )
    except Exception as exc:
        logger.debug("react-select %s / %s: %s", field_id, label_text[:30], exc)
    return False


def avaliar_preenchimento(vaga, resume: dict, config_dados: dict | None = None) -> dict:
    """Mede quanto do formulário conseguimos responder, sem abrir browser.

    A API pública do Greenhouse devolve as perguntas do formulário. Rodamos o
    mesmo `_auto_answer` que a candidatura real usaria e contamos o que fica sem
    resposta — que é exatamente o que viraria pergunta manual.
    """
    if config_dados is None:
        from jobapplier.config.manager import ConfigManager

        config_dados = ConfigManager().get("dados_pessoais") or {}

    identidade = resolver_identidade(vaga)
    if identidade is None:
        return montar_avaliacao(
            "greenhouse",
            Descoberta(StatusDescoberta.RESPOSTA_INVALIDA,
                       detalhe=f"link não reconhecido: {getattr(vaga, 'link', '')[:80]}"),
        )

    descoberta = descobrir_perguntas(identidade.slug, identidade.job_id)
    if not descoberta.ok:
        # Sem leitura do formulário não há confiança: None, nunca 0.0. Zero
        # pareceria uma medição válida dizendo "não dá para preencher".
        return montar_avaliacao("greenhouse", descoberta)

    normalizado = getattr(vaga, "normalizado_json", None) or {}

    obr_ok: list[str] = []
    obr_nok: list[str] = []
    opc_ok: list[str] = []
    opc_nok: list[str] = []
    bloqueios: list[Bloqueio] = []

    if not (config_dados.get("cpf") or "").strip():
        bloqueios.append(Bloqueio(
            CodigoBloqueio.CPF_AUSENTE, "configure em Setup → Etapa 3",
        ))

    for p in descoberta.perguntas:
        if p.nome_campo in CAMPOS_PADRAO:
            continue  # nome, e-mail, currículo: sempre preenchíveis

        if any(ph in p.label.lower() for ph in _us_auth_phrases_globais()):
            bloqueios.append(Bloqueio(CodigoBloqueio.WORK_AUTHORIZATION, p.label[:80]))
            continue

        if p.tipo in TIPOS_NAO_SUPORTADOS:
            bloqueios.append(Bloqueio(
                CodigoBloqueio.TIPO_NAO_SUPORTADO, f"{p.label[:60]} (tipo {p.tipo})",
            ))
            continue

        resposta = _auto_answer(
            p.label, p.tipo, p.opcoes, resume, normalizado, config_dados,
        )
        if p.obrigatoria:
            (obr_ok if resposta else obr_nok).append(p.label[:80])
        else:
            (opc_ok if resposta else opc_nok).append(p.label[:80])

    return montar_avaliacao(
        "greenhouse", descoberta,
        obrigatorias_conhecidas=obr_ok, obrigatorias_desconhecidas=obr_nok,
        opcionais_conhecidas=opc_ok, opcionais_desconhecidas=opc_nok,
        bloqueios=bloqueios,
    )


def _us_auth_phrases_globais() -> tuple[str, ...]:
    """Frases que indicam vaga exclusiva dos EUA.

    Vivia dentro de `apply()`; extraída para a avaliação usar o mesmo critério —
    duas listas divergentes dariam confiança alta a uma vaga que a candidatura
    depois recusaria.
    """
    return (
        "authorized to work in the united states",
        "legally authorized to work in the us",
        "authorized to work in the us ",
        "h-1b visa status",
        "citizen or resident of",
        "sponsorship for employment visa",
    )


def apply(vaga, resume: dict, pdf_path: Path, cover_letter: str | None,
          visivel: bool = False, ao_verificar=None) -> dict:
    """Submete candidatura via Playwright (form submission real no Greenhouse).

    `visivel=True` abre o navegador na tela, e `ao_verificar` é chamado quando a
    plataforma exige verificação humana para submeter — recebe a `page` e
    devolve True se a candidatura foi confirmada. Os dois existem para
    `scripts/finalizar.py`, a sessão em que o candidato está presente e clica
    em enviar ele mesmo.

    São parâmetros e não uma segunda função de propósito: um `apply_visivel`
    paralelo seria uma cópia destas 279 linhas, e cópia diverge — o formulário
    do Greenhouse muda, uma das duas é corrigida, e a outra passa a enviar
    errado sem ninguém perceber.
    """
    from playwright.sync_api import sync_playwright

    from jobapplier.config.manager import ConfigManager
    config_dados = ConfigManager().get("dados_pessoais") or {}

    # Pré-validação: CPF obrigatório para Greenhouse brasileiro
    cpf = config_dados.get("cpf", "").strip()
    if not cpf:
        logger.warning("CPF não configurado — candidatura não enviada.")
        return resultado(
            REVISAO_MANUAL,
            "CPF não configurado. Configure em Setup → Etapa 3 → Dados pessoais.",
            perguntas_manuais=["Qual é o seu CPF? (configure em Setup → Etapa 3)"],
        )

    link = getattr(vaga, "link", "") or ""
    identidade = resolver_identidade(vaga)
    if identidade is None:
        return resultado(FALHA_AUTOMACAO, f"Link inválido: {link}")

    slug, job_id = identidade.slug, identidade.job_id
    normalizado = getattr(vaga, "normalizado_json", None) or {}
    job_url = f"{BOARD_BASE}/{slug}/jobs/{job_id}"
    logger.info("Candidatando via Playwright: %s", job_url)

    questions = _get_job_questions(slug, job_id)

    # Detecta vagas exclusivas dos EUA (requerem work authorization americana)
    _us_auth_phrases = _us_auth_phrases_globais()
    us_only_questions = [
        q.get("label", "") for q in questions
        if any(ph in q.get("label", "").lower() for ph in _us_auth_phrases)
    ]
    if us_only_questions:
        logger.info("Vaga US-only detectada (%s) — pulando.", slug)
        return resultado(
            REVISAO_MANUAL,
            "Vaga exclusiva para residentes nos EUA (requer work authorization americana).",
            perguntas_manuais=us_only_questions,
        )

    # Pré-calcula respostas
    answer_map: dict[str, dict] = {}
    perguntas_manuais: list[str] = []

    for q in questions:
        fields = q.get("fields", [])
        if not fields:
            continue
        field = fields[0]
        field_name = field.get("name", "")
        field_type = field.get("type", "")
        values = field.get("values", [])
        label = q.get("label", field_name)
        required = q.get("required", False)

        if field_name in CAMPOS_PADRAO:
            continue

        ans = _auto_answer(label, field_type, values, resume, normalizado, config_dados)

        if ans is not None:
            answer_map[field_name] = {
                "type": field_type,
                "values": values,
                "answer": ans,
                "label": label,
            }
            logger.debug("Auto-resposta '%s': %s", label[:40], str(ans)[:30])
        elif required:
            perguntas_manuais.append(label)
            logger.warning("Sem resposta automática para: %s", label)

    nome_completo = resume.get("nome", "").strip()
    partes = nome_completo.split()
    first_name = partes[0] if partes else ""
    last_name = " ".join(partes[1:]) if len(partes) > 1 else first_name

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not visivel, slow_mo=80)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="pt-BR",
        )
        page = context.new_page()

        try:
            page.goto(job_url, timeout=30000, wait_until="networkidle")
        except Exception:
            page.goto(job_url, timeout=30000, wait_until="domcontentloaded")

        page.wait_for_timeout(1500)

        # ── Campos padrão ──────────────────────────────────────────────────
        _pw_fill_text(page, "#first_name", first_name)
        _pw_fill_text(page, "#last_name", last_name)
        _pw_fill_text(page, "#email", resume.get("email", ""))
        _pw_fill_text(page, "#phone", resume.get("telefone", ""))

        # Localização do candidato
        _pw_fill_text(page, "#candidate-location", resume.get("localizacao", "São Paulo, SP"))

        # Upload do currículo PDF
        if pdf_path and pdf_path.exists():
            try:
                resume_input = page.query_selector("input#resume[type=file]")
                if resume_input:
                    resume_input.set_input_files(str(pdf_path))
                    logger.info("PDF uploaded: %s", pdf_path.name)
            except Exception as exc:
                logger.warning("Erro ao fazer upload do PDF: %s", exc)

        # Cover letter. Nos formulários novos do Greenhouse o textarea não existe
        # até clicar em "Enter manually": o campo nasce como quatro botões
        # (Attach / Dropbox / Google Drive / Enter manually). Sem esse clique a
        # carta simplesmente não entrava — e nada acusava, porque o applicator
        # tratava textarea ausente como "esta vaga não pede carta".
        if cover_letter:
            cl_area = page.query_selector("textarea#cover_letter_body")
            if not cl_area:
                botao_manual = page.query_selector("button:has-text('Enter manually')")
                if botao_manual:
                    try:
                        botao_manual.click()
                        page.wait_for_timeout(800)
                        cl_area = page.query_selector(
                            "textarea#cover_letter_body, textarea[id*='cover'], "
                            "textarea[name*='cover']"
                        )
                    except Exception as exc:
                        logger.warning("Erro ao abrir a carta manual: %s", exc)
            if cl_area:
                cl_area.fill(cover_letter[:8000])
            else:
                cl_text_area = page.query_selector("#cover_letter_text")
                if cl_text_area:
                    cl_text_area.fill(cover_letter[:8000])
                else:
                    logger.warning("Carta gerada, mas nenhum campo aceitou o texto.")

        # ── Perguntas customizadas ─────────────────────────────────────────
        for field_name, info in answer_map.items():
            field_type = info["type"]
            values_list = info["values"]
            answer = info["answer"]

            if field_type in ("input_text", "textarea"):
                _pw_fill_text(page, f'[id="{field_name}"]', str(answer))

            elif field_type == "input_file":
                pass  # Arquivos opcionais (laudo médico etc.) — pular

            elif field_type == "multi_value_single_select":
                label_text = _value_to_label(values_list, str(answer)) or str(answer)
                if label_text:
                    _pw_select_react(page, field_name, label_text)

            elif field_type == "multi_value_multi_select":
                # A API chama isto de multi-select, mas o Greenhouse renderiza de
                # duas formas diferentes: dropdown react-select quando há várias
                # opções, e CHECKBOX quando há uma só — o caso dos consentimentos
                # obrigatórios. Tratar checkbox como dropdown fazia o applicator
                # esperar 4s por uma lista que nunca abre e desistir em silêncio,
                # deixando um campo obrigatório em branco com a resposta já
                # calculada na mão.
                answer_list = answer if isinstance(answer, list) else [answer]
                for val in answer_list:
                    if _pw_marcar_checkbox(page, field_name, str(val)):
                        page.wait_for_timeout(200)
                        continue
                    label_text = _value_to_label(values_list, str(val)) or str(val)
                    if label_text:
                        _pw_select_react(page, field_name, label_text)
                        page.wait_for_timeout(300)

        # ── Checkboxes de consentimento / política ─────────────────────────
        _consent_keywords = [
            "acknowledge", "privacy", "data protection", "responsible use",
            "i confirm", "i have read", "email me", "job alerts",
        ]
        try:
            checkboxes = page.query_selector_all("input[type=checkbox]")
            for cb in checkboxes:
                try:
                    label_el = page.query_selector(f'label[for="{cb.get_attribute("id")}"]')
                    label_text = (label_el.inner_text() if label_el else cb.get_attribute("aria-label") or "").lower()
                    if any(kw in label_text for kw in _consent_keywords):
                        if not cb.is_checked():
                            cb.check()
                except Exception:
                    pass
        except Exception:
            pass

        page.wait_for_timeout(800)

        # ── Submit ─────────────────────────────────────────────────────────
        submit_btn = (
            page.query_selector("button[type=submit][data-submits=true]")
            or page.query_selector("button[type=submit]")
            or page.query_selector("input[type=submit]")
        )

        if not submit_btn:
            evidencias = capturar_falha(page, "greenhouse", getattr(vaga, "id", "?"))
            browser.close()
            return resultado(FALHA_AUTOMACAO, "Botão de submit não encontrado na página",
                             perguntas_manuais=perguntas_manuais, evidencias=evidencias)

        submit_btn.click()

        # Sinal FORTE: o Greenhouse redireciona para uma URL de confirmação
        # própria. Isso é prova; texto na página não é.
        url_confirmacao = False
        try:
            page.wait_for_url(re.compile(r"confirmation|application_confirmation"), timeout=15000)
            url_confirmacao = True
        except Exception:
            pass

        final_url = page.url
        content = page.content().lower()

        sinais_fortes = {
            "url de confirmação": url_confirmacao or "confirmation" in final_url.lower(),
            "elemento de confirmação": page.query_selector(
                "#application_confirmation, .application-confirmation, "
                "[data-testid*='confirmation']"
            ) is not None,
        }
        # FRACOS: texto genérico. "obrigado" sozinho marcava sucesso antes e
        # casa com qualquer rodapé de agradecimento.
        sinais_fracos = {
            "texto de agradecimento": ("obrigado" in content or "thank" in content),
            "texto de candidatura enviada": ("candidatura" in content and "enviada" in content),
        }

        # O envio parou num passo que só um humano passa? Isso NÃO é falha: o
        # formulário foi preenchido inteiro e a plataforma pediu prova de que há
        # gente do outro lado. Sem esta checagem a Adyen virava "nenhum sinal de
        # submissão", indistinguível de seletor quebrado.
        verificacao_humana = _pede_verificacao_humana(page, content)

        # Sessão assistida: o candidato está na frente da tela. O gancho preenche
        # o código e espera o clique DELE no botão real. Nada aqui clica em
        # enviar — se o gancho devolver False, o desfecho segue sendo
        # "aguardando verificação", nunca "enviada".
        if verificacao_humana and ao_verificar is not None:
            if ao_verificar(page):
                sinais_fortes["confirmação em sessão assistida"] = True
                verificacao_humana = False
                content = page.content().lower()

        # Captura possíveis erros de validação
        validation_errors = []
        try:
            error_els = page.query_selector_all("[role=alert], .error-message, .field-error, [class*='error']")
            for el in error_els[:5]:
                txt = (el.inner_text() or "").strip()
                if txt and len(txt) < 200:
                    validation_errors.append(txt)
        except Exception:
            pass

        # Evidência antes de fechar: sem sucesso, o PNG/HTML é o que permite
        # descobrir se o formulário mudou de layout. Este apply() não tem
        # try/except de topo — uma exceção sobe para o orquestrador, que marca a
        # vaga como erro; aqui cobrimos a falha silenciosa, que é o caso comum.
        evidencias = []
        if not any(sinais_fortes.values()):
            evidencias = capturar_falha(page, "greenhouse", getattr(vaga, "id", "?"))

        browser.close()

    status, justificativa = avaliar_confirmacao(
        sinais_fortes, perguntas_manuais=perguntas_manuais,
        sinais_fracos=sinais_fracos, verificacao_humana=verificacao_humana,
    )
    if validation_errors and status != ENVIADA_CONFIRMADA:
        justificativa += f". Erros de validação: {'; '.join(validation_errors)}"

    logger.log(
        logging.INFO if status == ENVIADA_CONFIRMADA else logging.WARNING,
        "Greenhouse: %s — %s", status, justificativa,
    )
    return resultado(status, justificativa,
                     perguntas_manuais=perguntas_manuais, evidencias=evidencias)
