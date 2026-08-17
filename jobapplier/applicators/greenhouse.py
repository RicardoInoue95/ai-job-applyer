"""Módulo 13 — Candidatura via Greenhouse usando Playwright (form submission real)."""
import logging
import re
from pathlib import Path

import requests

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
    techs_resume = [t.lower() for t in resume.get("tecnologias", [])]
    experiencias = resume.get("experiencias", [])
    cargo_atual = experiencias[0].get("cargo", "") if experiencias else ""
    empresa_atual = experiencias[0].get("empresa", "") if experiencias else ""

    if "cpf" in label_lower:
        return config_dados.get("cpf") or None

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

    # Cidade de residência
    if any(k in label_lower for k in ["cidade", "reside", "onde você mora"]):
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

    if any(k in label_lower for k in ["consentimento", "consent", "análise do seu perfil", "analise do seu perfil", "otimizar a análise"]):
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
    ]):
        if field_type in ("input_text", "textarea"):
            return "LinkedIn"
        val = (_pick_value(values, "LinkedIn") or _pick_value(values, "Glassdoor")
               or _pick_value(values, "Job Board") or _pick_value(values, "Other"))
        if val:
            return [val] if field_type == "multi_value_multi_select" else val

    # Salary expectation
    if any(k in label_lower for k in [
        "salary expectation", "pretensão salarial", "pretensao salarial",
        "remuneração esperada", "salário desejado", "salary range", "compensation",
    ]):
        # Sem valor configurado, NÃO responde. O fallback anterior escrevia
        # "A combinar" — não é mentira, mas é uma decisão de negociação tomada
        # em nome do usuário, que nunca a configurou. Alguns recrutadores
        # descartam "a combinar"; outros esperam um número. É preferência do
        # candidato, e preferência ausente vira pergunta manual.
        #
        # Configure em dados_pessoais.salario (ou salario_esperado no currículo)
        # para voltar a preencher automaticamente — inclusive com "A combinar",
        # se essa for a sua escolha.
        salary = config_dados.get("salario") or resume.get("salario_esperado")
        if salary and field_type in ("input_text", "textarea"):
            return str(salary)
        return None

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

    # Previous employment at THIS company
    if any(k in label_lower for k in [
        "previously been employed", "previously worked for", "former employee",
        "worked here before", "have you worked at",
    ]) and _is_yes_no(field_type, values):
        return _no_value(values)

    # General work authorization in the COUNTRY (non-US-specific)
    if any(k in label_lower for k in [
        "authorized to work in the country", "authorised to work in the country",
        "right to work where this role",
    ]):
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

    if _is_diversidade(label):
        diversidade = config_dados.get("diversidade", {})
        if any(k in label_lower for k in ["deficiência", "deficiencia", "pcd"]):
            return (_pick_value(values, "Prefer not to answer")
                    or _pick_value(values, "Prefiro não responder")
                    or _pick_value(values, "No ("))
        if any(k in label_lower for k in ["gênero", "genero", "identidade de gênero"]):
            g = diversidade.get("genero", "")
            return _pick_value(values, g) if g else None
        if any(k in label_lower for k in ["orientação sexual", "orientacao sexual"]):
            o = diversidade.get("orientacao", "")
            return _pick_value(values, o) if o else None
        if any(k in label_lower for k in ["raça", "raca", "etnia"]):
            r = diversidade.get("raca", "")
            return _pick_value(values, r) if r else None

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


def _pw_select_react(page, field_id: str, label_text: str, timeout: int = 4000) -> bool:
    """Seleciona uma opção em um react-select dropdown."""
    bare_id = field_id.replace("[]", "")
    selector = f'[id="{field_id}"]'
    opt_selector = f'[id*="react-select-"][id*="{bare_id}"][id*="-option"]'
    try:
        page.click(selector, timeout=3000)
        page.wait_for_selector(opt_selector, timeout=timeout)
        options = page.query_selector_all(opt_selector)
        for opt in options:
            if label_text.lower() in (opt.inner_text() or "").lower():
                opt.click()
                return True
        # Fallback: type to filter
        page.fill(selector, label_text[:20])
        page.wait_for_timeout(600)
        for opt in page.query_selector_all(opt_selector):
            if label_text.lower() in (opt.inner_text() or "").lower():
                opt.click()
                return True
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


def apply(vaga, resume: dict, pdf_path: Path, cover_letter: str | None) -> dict:
    """Submete candidatura via Playwright (form submission real no Greenhouse)."""
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
        browser = pw.chromium.launch(headless=True, slow_mo=80)
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

        # Cover letter (textarea ou file upload)
        if cover_letter:
            cl_area = page.query_selector("textarea#cover_letter_body")
            if cl_area:
                cl_area.fill(cover_letter[:8000])
            else:
                cl_text_area = page.query_selector("#cover_letter_text")
                if cl_text_area:
                    cl_text_area.fill(cover_letter[:8000])

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
                answer_list = answer if isinstance(answer, list) else [answer]
                for val in answer_list:
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
        sinais_fortes, perguntas_manuais=perguntas_manuais, sinais_fracos=sinais_fracos,
    )
    if validation_errors and status != ENVIADA_CONFIRMADA:
        justificativa += f". Erros de validação: {'; '.join(validation_errors)}"

    logger.log(
        logging.INFO if status == ENVIADA_CONFIRMADA else logging.WARNING,
        "Greenhouse: %s — %s", status, justificativa,
    )
    return resultado(status, justificativa,
                     perguntas_manuais=perguntas_manuais, evidencias=evidencias)
