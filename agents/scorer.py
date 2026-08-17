"""Módulo 3 — Match IA com pesos.

Avalia aderência entre currículo JSON e vaga normalizada.
Pesos: Skills 40%, Senioridade 20%, Setor 15%, Idioma 15%, Localização 10%
"""
import json
import logging
from datetime import date
from typing import TYPE_CHECKING


def _parse_mes_ano(s: str) -> date | None:
    """Converte 'MM/YYYY' em date(YYYY, MM, 1). Retorna None se inválido."""
    try:
        mes, ano = s.strip().split("/")
        return date(int(ano), int(mes), 1)
    except Exception:
        return None


def _calc_anos_exp(experiencias: list[dict], today: date) -> float:
    """Soma os meses de todas as experiências e retorna anos (float, 1 casa)."""
    total_meses = 0
    for e in experiencias:
        inicio = _parse_mes_ano(e.get("data_inicio") or "")
        fim_str = e.get("data_fim") or ""
        fim = _parse_mes_ano(fim_str) if fim_str else today
        if inicio and fim and fim >= inicio:
            total_meses += (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    return round(total_meses / 12, 1)

if TYPE_CHECKING:
    from agents.llm import LLMClient

logger = logging.getLogger(__name__)

SCORE_PROMPT = """Você é um avaliador especialista em recrutamento de tecnologia no Brasil.

DATA DE HOJE: {today}
CARGO ATUAL DO CANDIDATO: {cargo_atual} em {empresa_atual} (desde {inicio_atual})
TEMPO TOTAL DE EXPERIÊNCIA EM DADOS: {anos_exp} anos

CURRÍCULO DO CANDIDATO (JSON):
{resume_json}

VAGA NORMALIZADA (JSON):
{vaga_json}

Avalie a aderência do candidato à vaga usando os critérios e pesos abaixo.
Seja criterioso mas justo. Considere equivalências tecnológicas (ex: Azure Data Factory ≈ AWS Glue).

CRITÉRIOS (soma = 100 pontos):
1. skills_tecnicas (40 pts): sobreposição entre tecnologias do currículo e da vaga
2. senioridade (20 pts): alinhamento entre nível exigido e experiência do candidato
3. setor (15 pts): experiência prévia no setor da empresa (ex: fintech, saúde, varejo)
4. idioma (15 pts): idioma exigido vs idiomas do currículo com nível adequado
5. localizacao (10 pts): compatibilidade da modalidade/localização com o candidato

Retorne SOMENTE JSON válido:
{{
  "score": 0,
  "breakdown": {{
    "skills_tecnicas": 0,
    "senioridade": 0,
    "setor": 0,
    "idioma": 0,
    "localizacao": 0
  }},
  "motivos_positivos": ["lista de pontos fortes"],
  "gaps": ["lista de lacunas ou pontos fracos"],
  "resumo": "uma frase resumindo a aderência",
  "perfil_base_sugerido": "data_engineer|analytics_engineer|bi_analyst|cloud_data_engineer"
}}

O campo score deve ser a soma exata dos valores no breakdown."""


def _resolve_data_fim(data_fim: str | None, today_str: str) -> str:
    """Substitui data_fim None/vazia pelo dia de hoje."""
    if not data_fim:
        return today_str
    return data_fim


def score(vaga, resume_json: dict, client: "LLMClient") -> dict | None:
    """Retorna o resultado do scoring ou None em caso de erro."""
    today = date.today()
    today_str = today.strftime("%m/%Y")
    normalizado = getattr(vaga, "normalizado_json", None) or {}

    vaga_info = {
        "titulo": getattr(vaga, "titulo", ""),
        "empresa": getattr(vaga, "empresa", ""),
        "plataforma": getattr(vaga, "plataforma", ""),
        **normalizado,
    }

    experiencias_raw = resume_json.get("experiencias", [])

    # Experiência atual = primeira entrada (mais recente) com data_fim null
    exp_atual = next((e for e in experiencias_raw if not e.get("data_fim")), None) or (experiencias_raw[0] if experiencias_raw else {})
    cargo_atual = exp_atual.get("cargo", "não informado")
    empresa_atual = exp_atual.get("empresa", "não informada")
    inicio_atual = exp_atual.get("data_inicio", "?")

    anos_exp = _calc_anos_exp(experiencias_raw, today)

    # Substitui data_fim None pela data atual para cálculo correto de duração
    resume_resumido = {
        "nome": resume_json.get("nome", ""),
        "localizacao": resume_json.get("localizacao", ""),
        "resumo_profissional": resume_json.get("resumo_profissional", ""),
        "tecnologias": resume_json.get("tecnologias", []),
        "idiomas": resume_json.get("idiomas", []),
        "soft_skills": resume_json.get("soft_skills", []),
        "experiencias": [
            {
                "empresa": e.get("empresa", ""),
                "cargo": e.get("cargo", ""),
                "data_inicio": e.get("data_inicio", ""),
                "data_fim": _resolve_data_fim(e.get("data_fim"), today_str),
                "tecnologias": e.get("tecnologias", []),
            }
            for e in experiencias_raw
        ],
    }

    prompt = SCORE_PROMPT.format(
        today=today_str,
        cargo_atual=cargo_atual,
        empresa_atual=empresa_atual,
        inicio_atual=inicio_atual,
        anos_exp=anos_exp,
        resume_json=json.dumps(resume_resumido, ensure_ascii=False, indent=2),
        vaga_json=json.dumps(vaga_info, ensure_ascii=False, indent=2),
    )

    try:
        result = client.generate_json(prompt, temperature=0.1)
        if isinstance(result, dict) and "score" in result:
            # Garante que o score está no range 0-100
            result["score"] = max(0, min(100, float(result.get("score", 0))))
            return result
        logger.warning("Scorer retornou formato inesperado: %s", result)
        return None
    except Exception as exc:
        logger.error("Erro ao pontuar vaga id=%s: %s", getattr(vaga, "id", "?"), exc)
        return None
