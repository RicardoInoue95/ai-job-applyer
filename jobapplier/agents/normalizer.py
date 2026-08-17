"""Módulo 2 — Normalização via Gemini.

Recebe descrição bruta e extrai campos estruturados em JSON.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobapplier.llm import LLMClient

logger = logging.getLogger(__name__)

NORMALIZE_PROMPT = """Analise a descrição da vaga abaixo e extraia as informações em JSON estruturado.

VAGA:
Título: {titulo}
Empresa: {empresa}
Localização: {localizacao}
Descrição:
{descricao}

Retorne SOMENTE o JSON com os campos abaixo. Nunca invente informações — use null quando não disponível.

{{
  "cargo": "título normalizado e limpo da vaga",
  "senioridade": "Junior|Pleno|Senior|Especialista|Gerente|Desconhecida",
  "tecnologias": ["lista", "de", "tecnologias", "e", "ferramentas", "mencionadas"],
  "anos_experiencia_minimo": null,
  "localizacao": "cidade ou Remoto",
  "modalidade": "Remoto|Híbrido|Presencial|Desconhecida",
  "salario": null,
  "soft_skills": ["lista", "de", "soft", "skills"],
  "idioma_principal": "Português|Inglês|Espanhol|Desconhecida",
  "setor_empresa": "setor de atuação da empresa ex: Fintech, E-commerce, Saúde"
}}"""


def normalize(vaga, client: "LLMClient") -> dict | None:
    """Normaliza uma vaga via Gemini. Retorna o dict ou None em caso de erro."""
    titulo = getattr(vaga, "titulo", "") or ""
    empresa = getattr(vaga, "empresa", "") or ""
    localizacao = getattr(vaga, "localizacao", "") or ""
    descricao = getattr(vaga, "descricao", "") or ""

    # Trunca descrições muito longas para economizar tokens
    if len(descricao) > 4000:
        descricao = descricao[:4000] + "...[truncado]"

    prompt = NORMALIZE_PROMPT.format(
        titulo=titulo,
        empresa=empresa,
        localizacao=localizacao,
        descricao=descricao,
    )

    try:
        result = client.generate_json(prompt, temperature=0.1)
        if isinstance(result, dict):
            return result
        logger.warning("Normalizer retornou tipo inesperado: %s", type(result))
        return None
    except Exception as exc:
        logger.error("Erro ao normalizar vaga id=%s: %s", getattr(vaga, "id", "?"), exc)
        return None
