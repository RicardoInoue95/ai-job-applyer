import json
import logging
from pathlib import Path

from agents.gemini_client import GeminiClient
from resume_parser.exceptions import ResumeParserError
from resume_parser.extractors import get_extractor
from resume_parser.models import PerfilBase, ResumeJSON
from resume_parser.parsers import GeminiResumeParser

logger = logging.getLogger(__name__)

PROFILES = [
    ("data_engineer", "Engenheiro de Dados"),
    ("analytics_engineer", "Analytics Engineer"),
    ("bi_analyst", "Analista de BI"),
    ("cloud_data_engineer", "Engenheiro de Dados Cloud"),
]

PROFILE_PROMPT = """Você é um especialista em currículos para tecnologia no Brasil.

Dado o currículo completo abaixo, crie uma versão focada no perfil: {perfil_nome}.

CURRÍCULO COMPLETO:
{resume_json}

Para o perfil "{perfil_nome}", selecione e destaque:
- As experiências mais relevantes para esse papel (máximo 4, em ordem de relevância)
- As tecnologias mais relevantes para esse perfil
- Adapte o resumo profissional para enfatizar esse ângulo
- Mantenha apenas certificações relevantes para o perfil

Retorne JSON com a mesma estrutura do currículo completo, mas focado neste perfil.
Adicione o campo "perfil": "{perfil_id}" ao JSON.
NÃO invente informações — use apenas o que está no currículo original.
"""


class ResumePipeline:
    def __init__(self, api_key: str):
        self.client = GeminiClient(api_key=api_key, use_cache=True)
        self.parser = GeminiResumeParser(self.client)

    def parse_file(self, file_path: Path) -> ResumeJSON:
        extractor = get_extractor(file_path)
        text = extractor.extract()
        logger.info("Texto extraído: %d chars de %s", len(text), file_path.name)
        return self.parser.parse(text)

    def generate_base_profiles(
        self, resume: ResumeJSON, output_dir: Path
    ) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        resume_json_str = json.dumps(resume.model_dump(), ensure_ascii=False, indent=2)
        generated = {}

        for profile_id, profile_name in PROFILES:
            prompt = PROFILE_PROMPT.format(
                perfil_id=profile_id,
                perfil_nome=profile_name,
                resume_json=resume_json_str,
            )
            try:
                data = self.client.generate_json(prompt, temperature=0.0)
                data["perfil"] = profile_id
                profile = PerfilBase.model_validate(data)

                output_path = output_dir / f"resume_base_{profile_id}.json"
                output_path.write_text(
                    json.dumps(profile.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                generated[profile_id] = output_path
                logger.info("Perfil %s gerado em %s", profile_id, output_path)
            except Exception as exc:
                logger.error("Erro ao gerar perfil %s: %s", profile_id, exc)

        return generated

    def run(
        self, file_path: Path, output_dir: Path
    ) -> tuple[ResumeJSON, dict[str, Path]]:
        resume = self.parse_file(file_path)
        profiles = self.generate_base_profiles(resume, output_dir)
        return resume, profiles
