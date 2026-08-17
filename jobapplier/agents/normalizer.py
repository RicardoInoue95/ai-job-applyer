"""Módulo 2 — Normalização.

Recebe descrição bruta e extrai campos estruturados em JSON. Dois caminhos com o
mesmo formato de saída: extração determinística (padrão, sem custo) e LLM.
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


def normalize(vaga, client: "LLMClient | None" = None) -> dict | None:
    """Normaliza uma vaga. Retorna o dict ou None em caso de erro.

    Sem ``client``, usa extração determinística — sem rede e sem custo. É o
    caminho padrão quando não há provedor de LLM configurado, e cobre a etapa de
    maior volume do pipeline: normalizar é extrair, não julgar.

    Com ``client``, usa o modelo. Ganha em descrição mal escrita e em tecnologia
    fora do vocabulário; perde em custo e em reprodutibilidade.
    """
    if client is None:
        from jobapplier.agents.extracao import normalizar

        return normalizar(vaga)

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
