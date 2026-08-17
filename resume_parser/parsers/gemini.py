import json
import logging
from agents.gemini_client import GeminiClient
from resume_parser.models import ResumeJSON
from resume_parser.exceptions import ParseError
from .base import BaseResumeParser

logger = logging.getLogger(__name__)

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
"""


class GeminiResumeParser(BaseResumeParser):
    def __init__(self, client: GeminiClient):
        self.client = client

    def parse(self, text: str) -> ResumeJSON:
        prompt = PARSE_PROMPT.format(text=text[:12000])
        try:
            data = self.client.generate_json(prompt, temperature=0.0)
            return ResumeJSON.model_validate(data)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Gemini retornou JSON inválido: {exc}") from exc
        except Exception as exc:
            raise ParseError(f"Erro ao parsear currículo: {exc}") from exc
