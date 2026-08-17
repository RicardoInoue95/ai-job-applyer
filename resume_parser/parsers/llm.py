"""Módulo 16 — parser de currículo sobre qualquer provedor de LLM.

Antes era ``GeminiResumeParser``, acoplado ao Gemini. O prompt é agnóstico de
provedor: o que muda entre provedores é apenas como o JSON é solicitado, e isso
já está encapsulado em ``agents.llm``.
"""
import json
import logging
from typing import TYPE_CHECKING

from resume_parser.exceptions import ParseError
from resume_parser.models import ResumeJSON

from .base import BaseResumeParser

if TYPE_CHECKING:
    from agents.llm import LLMClient

logger = logging.getLogger(__name__)

#: Limite de caracteres enviados ao modelo. Currículos raramente passam disso e
#: o corte protege contra PDF com texto duplicado por camada.
MAX_CHARS = 12000

PARSE_PROMPT = """Você é um extrator especializado em currículos brasileiros.
Analise o texto abaixo e extraia todas as informações em formato JSON estruturado.

TEXTO DO CURRÍCULO:
{text}

Retorne um JSON com exatamente esta estrutura:
{{
  "nome": "Nome completo",
  "email": "email@exemplo.com ou null",
  "telefone": "+55 11 99999-9999 ou null",
  "linkedin": "URL do LinkedIn ou null",
  "github": "URL do GitHub ou null",
  "localizacao": "Cidade, Estado ou null",
  "resumo_profissional": "Resumo/objetivo profissional ou null",
  "experiencias": [
    {{
      "empresa": "Nome da empresa",
      "cargo": "Título do cargo",
      "data_inicio": "MM/AAAA ou null",
      "data_fim": "MM/AAAA ou null (null = atual)",
      "descricao": "Descrição das responsabilidades",
      "tecnologias": ["Tech1", "Tech2"],
      "conquistas": ["Conquista 1", "Conquista 2"]
    }}
  ],
  "formacao": [
    {{
      "instituicao": "Nome da instituição",
      "curso": "Nome do curso",
      "data_conclusao": "AAAA ou null",
      "em_andamento": false
    }}
  ],
  "certificacoes": [
    {{
      "nome": "Nome da certificação",
      "emissor": "Empresa emissora",
      "data": "AAAA ou null",
      "link": "URL ou null"
    }}
  ],
  "idiomas": [
    {{
      "nome": "Português",
      "nivel": "Nativo"
    }}
  ],
  "tecnologias": ["Lista completa de todas as tecnologias mencionadas"],
  "soft_skills": ["Comunicação", "Liderança", etc]
}}

Extraia TODAS as tecnologias mencionadas em qualquer seção do currículo para o campo "tecnologias".
Mantenha nomes de tecnologias na ortografia original (ex: Python, SQL, Apache Spark).
NÃO invente informação que não esteja no texto — campo ausente vira null.
"""


class LLMResumeParser(BaseResumeParser):
    """Extrai ResumeJSON de texto de currículo usando o LLM configurado."""

    def __init__(self, client: "LLMClient | None" = None):
        if client is None:
            from agents.llm import get_client

            client = get_client()
        self.client = client

    def parse(self, text: str) -> ResumeJSON:
        if not text or not text.strip():
            raise ParseError("Texto do currículo está vazio — a extração falhou.")

        prompt = PARSE_PROMPT.format(text=text[:MAX_CHARS])
        try:
            dados = self.client.generate_json(prompt, temperature=0.0)
        except json.JSONDecodeError as exc:
            raise ParseError(f"LLM retornou JSON inválido: {exc}") from exc
        except Exception as exc:
            raise ParseError(f"Erro ao parsear currículo: {exc}") from exc

        try:
            return ResumeJSON.model_validate(dados)
        except Exception as exc:
            raise ParseError(
                f"JSON do LLM não corresponde ao schema esperado: {exc}"
            ) from exc


#: Nome antigo, mantido para importações existentes.
GeminiResumeParser = LLMResumeParser
