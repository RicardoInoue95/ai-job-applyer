"""Módulo 12 — Resume Optimization Engine.

Recebe um perfil base JSON e dados da vaga normalizada.
Reescreve o resumo e descrições usando terminologia da vaga.
Nunca inventa fatos — apenas reformula o que já existe.
"""
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobapplier.llm import LLMClient

logger = logging.getLogger(__name__)

OPTIMIZE_PROMPT = """Você é um especialista em otimização de currículos para ATS (Applicant Tracking Systems) no Brasil.

VAGA ALVO:
{vaga_json}

CURRÍCULO BASE (JSON):
{resume_json}

TAREFA:
Reescreva o currículo para maximizar a aderência à vaga, seguindo estas regras ABSOLUTAS:
1. NUNCA invente experiências, empresas, cargos, datas, certificações ou tecnologias que não existam no original
2. PODE reordenar tecnologias, reformular descrições com terminologia da vaga, ajustar ênfase
3. PODE incluir keywords da vaga quando elas descrevem algo que o candidato genuinamente faz/fez
4. Mantenha o mesmo tom profissional e terceira pessoa (ex: "Construção de pipelines...", não "Construí...")

FORMATO DAS DESCRIÇÕES (obrigatório):
- O campo "descricao" de cada experiência deve ser uma LISTA de strings (array JSON)
- Cada item da lista = um bullet point curto e direto (máximo 120 caracteres)
- Entre 3 e 6 bullets por experiência
- O campo "conquistas" deve também ser lista de strings com resultados mensuráveis
- Exemplo correto:
  "descricao": [
    "Construção e orquestração de pipelines ETL/ELT em Snowflake e Azure Data Factory",
    "Modelagem analítica em camadas bronze, silver e gold com dbt",
    "Integração de APIs REST e fontes SaaS para ingestão de dados"
  ]

Retorne SOMENTE o JSON do currículo otimizado com a mesma estrutura do original.
Modifique APENAS: resumo_profissional, descricao das experiências (como lista), conquistas, e a ordem de tecnologias.
Não altere: nome, email, linkedin, localizacao, empresa, cargo, datas, formacao, certificacoes, idiomas."""


def _calc_ats_score(resume_techs: list[str], job_techs: list[str]) -> tuple[float, list[str], list[str]]:
    """Calcula score ATS: keywords da vaga presentes no currículo."""
    if not job_techs:
        return 0.0, [], []
    resume_lower = {t.lower() for t in resume_techs}
    matched = [t for t in job_techs if t.lower() in resume_lower]
    missing = [t for t in job_techs if t.lower() not in resume_lower]
    score = len(matched) / len(job_techs) * 100
    return round(score, 1), matched, missing


#: Campos que o prompt exige como lista de strings e que o LLM às vezes devolve
#: como string única — ou, pior, como string contendo o repr de uma lista.
_CAMPOS_LISTA_EXPERIENCIA = ("descricao", "conquistas", "tecnologias")


def _normalizar_saida(perfil: dict) -> dict:
    """Força os campos de lista a serem realmente listas de strings.

    A saída do LLM ia direto para o gerador de PDF, sem validação. Quando o
    modelo devolvia ``descricao`` como ``"['bullet um', 'bullet dois']"``, o
    currículo era impresso com colchetes e aspas e enviado assim ao recrutador.
    Normalizar aqui é a correção na origem; `pdf.normalizar_itens` é a rede.
    """
    from jobapplier.generators.pdf import normalizar_itens

    if not isinstance(perfil, dict):
        return perfil

    for chave in ("tecnologias", "soft_skills", "idiomas"):
        if chave in perfil and not isinstance(perfil[chave], list):
            perfil[chave] = normalizar_itens(perfil[chave])

    experiencias = perfil.get("experiencias")
    if isinstance(experiencias, list):
        for exp in experiencias:
            if not isinstance(exp, dict):
                continue
            for chave in _CAMPOS_LISTA_EXPERIENCIA:
                if chave in exp:
                    itens = normalizar_itens(exp[chave])
                    # 'descricao' aceita string única no schema legado; manter
                    # lista é o formato que o prompt pede e que o PDF renderiza
                    # como bullets.
                    exp[chave] = itens

    return perfil


def otimizar_sem_llm(base_profile: dict, vaga) -> dict:
    """Otimização por reordenação, sem reescrever nada.

    O ganho de ATS que não depende de modelo é ordenar: trazer para a frente
    as tecnologias que a vaga pede, entre as que o candidato realmente tem.
    Muitos parsers de ATS pesam as primeiras ocorrências.

    O que NÃO faz: reescrever resumo ou descrições. Isso exige geração, e
    inventar frase sem modelo seria pior que manter o texto original —
    invariante 3, o sistema não afirma o que o currículo não sustenta.
    """
    import copy

    from jobapplier import vocabulario as vocab

    perfil = copy.deepcopy(base_profile)
    normalizado = getattr(vaga, "normalizado_json", None) or {}
    tec_vaga = [vocab.canonizar(t) for t in (normalizado.get("tecnologias") or [])]

    def prioridade(tec: str) -> tuple[int, int]:
        canonico = vocab.canonizar(tec)
        if canonico in tec_vaga:
            return (0, tec_vaga.index(canonico))
        if any(vocab.sao_equivalentes(canonico, t) for t in tec_vaga):
            return (1, 0)
        return (2, 0)

    if isinstance(perfil.get("tecnologias"), list):
        perfil["tecnologias"] = sorted(perfil["tecnologias"], key=prioridade)

    for exp in perfil.get("experiencias") or []:
        if isinstance(exp, dict) and isinstance(exp.get("tecnologias"), list):
            exp["tecnologias"] = sorted(exp["tecnologias"], key=prioridade)

    return perfil


def optimize(base_profile: dict, vaga, client: "LLMClient | None" = None) -> dict:
    """Retorna dict com perfil otimizado + métricas ATS."""
    normalizado = getattr(vaga, "normalizado_json", None) or {}
    job_techs = normalizado.get("tecnologias", [])

    # ATS score antes da otimização
    resume_techs_orig = base_profile.get("tecnologias", [])
    ats_antes, matched_antes, _ = _calc_ats_score(resume_techs_orig, job_techs)

    # O idioma da vaga entra no prompt: currículo em português para vaga em
    # inglês perde no parsing do ATS, que casa termo literal, e não deixa erro
    # em lugar nenhum — o PDF sai bonito e os termos não batem.
    from jobapplier import idioma as mod_idioma

    lingua = mod_idioma.da_vaga(vaga)

    vaga_info = {
        "titulo": getattr(vaga, "titulo", ""),
        "empresa": getattr(vaga, "empresa", ""),
        "senioridade": normalizado.get("senioridade", ""),
        "tecnologias": job_techs,
        "soft_skills": normalizado.get("soft_skills", []),
        "idioma_principal": normalizado.get("idioma_principal", ""),
        "setor_empresa": normalizado.get("setor_empresa", ""),
    }

    prompt = OPTIMIZE_PROMPT.format(
        vaga_json=json.dumps(vaga_info, ensure_ascii=False, indent=2),
        resume_json=json.dumps(base_profile, ensure_ascii=False, indent=2),
    ) + mod_idioma.instrucao_para(lingua)

    if client is None:
        logger.info("Otimização sem LLM: reordenando tecnologias, sem reescrever texto.")
        otimizado = otimizar_sem_llm(base_profile, vaga)
        # O idioma do currículo é lido do próprio texto, não presumido: desde que
        # `perfis.montar` escolhe o mestre pelo idioma da vaga, presumir
        # português avisaria descompasso justamente quando não há nenhum. Aqui o
        # aviso sobra só para o caso real — o mestre daquele idioma não carregou.
        lingua_curriculo = mod_idioma.detectar(
            base_profile.get("resumo_profissional") or "")
        aviso = mod_idioma.descompasso(lingua, lingua_curriculo)
        if aviso:
            logger.warning("Vaga id=%s: %s", getattr(vaga, "id", "?"), aviso)
    else:
        try:
            otimizado = client.generate_json(prompt, temperature=0.2)
            if not isinstance(otimizado, dict):
                logger.warning("Optimizer retornou tipo inesperado, usando base sem alteração")
                otimizado = base_profile
        except Exception as exc:
            logger.error("Erro na otimização: %s", exc)
            otimizado = base_profile

    otimizado = _normalizar_saida(otimizado)

    # Depois da normalização e fora dos dois ramos: vale com e sem LLM, e o
    # modelo não opina sobre isto. A lista sai de `EQUIVALENCIAS`, que é curada
    # — deixar o modelo decidir o que é equivalente abriria a porta para ele
    # "equivaler" qualquer coisa que a vaga pedisse.
    from jobapplier import vocabulario as vocab

    otimizado["equivalencias"] = vocab.equivalencias_uteis(
        job_techs, otimizado.get("tecnologias") or [])

    # ATS score após otimização
    resume_techs_opt = otimizado.get("tecnologias", [])
    ats_depois, matched_depois, missing_depois = _calc_ats_score(resume_techs_opt, job_techs)
    keywords_adicionadas = [k for k in matched_depois if k not in matched_antes]

    return {
        "perfil_otimizado": otimizado,
        "ats_antes": ats_antes,
        "ats_depois": ats_depois,
        "keywords_adicionadas": keywords_adicionadas,
        "keywords_ausentes": missing_depois,
    }
