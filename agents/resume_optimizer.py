"""Módulo 12 — Resume Optimization Engine.

Recebe um perfil base JSON e dados da vaga normalizada.
Reescreve o resumo e descrições usando terminologia da vaga.
Nunca inventa fatos — apenas reformula o que já existe.
"""
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.gemini_client import GeminiClient

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


def optimize(base_profile: dict, vaga, client: "GeminiClient") -> dict:
    """Retorna dict com perfil otimizado + métricas ATS."""
    normalizado = getattr(vaga, "normalizado_json", None) or {}
    job_techs = normalizado.get("tecnologias", [])

    # ATS score antes da otimização
    resume_techs_orig = base_profile.get("tecnologias", [])
    ats_antes, matched_antes, _ = _calc_ats_score(resume_techs_orig, job_techs)

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
    )

    try:
        otimizado = client.generate_json(prompt, temperature=0.2)
        if not isinstance(otimizado, dict):
            logger.warning("Optimizer retornou tipo inesperado, usando base sem alteração")
            otimizado = base_profile
    except Exception as exc:
        logger.error("Erro na otimização: %s", exc)
        otimizado = base_profile

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
