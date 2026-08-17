"""Módulo 6 — Geração de Cover Letter personalizada."""
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

COVER_LETTER_PROMPT = """Você é um especialista em redação de cartas de apresentação para vagas de tecnologia no Brasil.

CANDIDATO:
Nome: {nome}
Cargo atual: {cargo_atual}
Tecnologias principais: {techs}

VAGA:
Empresa: {empresa}
Título: {titulo}
Senioridade: {senioridade}
Tecnologias da vaga: {techs_vaga}
Setor: {setor}

Escreva uma carta de apresentação profissional em português com:
- Máximo 300 palavras
- Tom profissional mas genuíno, sem exageros
- Primeiro parágrafo: apresentação e interesse genuíno na empresa/vaga
- Segundo parágrafo: 2-3 realizações concretas alinhadas à vaga (use apenas fatos do currículo)
- Terceiro parágrafo: motivação específica para esta empresa e disponibilidade
- Sem fórmulas genéricas como "venho por meio desta"
- Não use "prezado(a)" — comece direto com o conteúdo

Retorne SOMENTE o texto da carta, sem assunto, sem cabeçalho, sem assinatura."""


def generate(resume_json: dict, vaga, client: "GeminiClient") -> str | None:
    """Gera cover letter personalizada. Retorna texto ou None em caso de erro."""
    normalizado = getattr(vaga, "normalizado_json", None) or {}

    experiencias = resume_json.get("experiencias", [])
    cargo_atual = experiencias[0].get("cargo", "") if experiencias else ""
    techs_candidato = ", ".join(resume_json.get("tecnologias", [])[:12])
    techs_vaga = ", ".join(normalizado.get("tecnologias", [])[:10])

    prompt = COVER_LETTER_PROMPT.format(
        nome=resume_json.get("nome", ""),
        cargo_atual=cargo_atual,
        techs=techs_candidato,
        empresa=getattr(vaga, "empresa", ""),
        titulo=getattr(vaga, "titulo", ""),
        senioridade=normalizado.get("senioridade", "Pleno"),
        techs_vaga=techs_vaga,
        setor=normalizado.get("setor_empresa", "Tecnologia"),
    )

    try:
        texto = client.generate(prompt, temperature=0.4)
        return texto.strip() if texto else None
    except Exception as exc:
        logger.error("Erro ao gerar cover letter para vaga id=%s: %s", getattr(vaga, "id", "?"), exc)
        return None
