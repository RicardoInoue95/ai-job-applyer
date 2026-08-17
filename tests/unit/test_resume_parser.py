import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jobapplier.resume_parser.exceptions import ParseError, UnsupportedFormatError
from jobapplier.resume_parser.models import ResumeJSON

SAMPLE_RESUME_JSON = {
    "nome": "Ricardo Inoue",
    "email": "ricardo@example.com",
    "telefone": "+55 11 99999-9999",
    "linkedin": "https://linkedin.com/in/ricardoinoue",
    "github": None,
    "localizacao": "São Paulo, SP",
    "resumo_profissional": "Engenheiro de dados com 5 anos de experiência.",
    "experiencias": [
        {
            "empresa": "Acme Corp",
            "cargo": "Data Engineer",
            "data_inicio": "01/2022",
            "data_fim": None,
            "descricao": "Pipeline de dados com Spark e Airflow",
            "tecnologias": ["Python", "Apache Spark", "Airflow"],
            "conquistas": ["Reduziu latência em 40%"],
        }
    ],
    "formacao": [
        {
            "instituicao": "USP",
            "curso": "Ciência da Computação",
            "data_conclusao": "2019",
            "em_andamento": False,
        }
    ],
    "certificacoes": [],
    "idiomas": [
        {"nome": "Português", "nivel": "Nativo"},
        {"nome": "Inglês", "nivel": "Avançado"},
    ],
    "tecnologias": ["Python", "SQL", "Apache Spark", "Airflow", "PostgreSQL"],
    "soft_skills": ["Comunicação", "Trabalho em equipe"],
}


def test_resume_json_validation():
    resume = ResumeJSON.model_validate(SAMPLE_RESUME_JSON)
    assert resume.nome == "Ricardo Inoue"
    assert len(resume.experiencias) == 1
    assert resume.experiencias[0].cargo == "Data Engineer"
    assert "Python" in resume.tecnologias


def test_resume_json_missing_optional_fields():
    minimal = {"nome": "Test User"}
    resume = ResumeJSON.model_validate(minimal)
    assert resume.nome == "Test User"
    assert resume.email is None
    assert resume.experiencias == []
    assert resume.tecnologias == []


def test_unsupported_format_raises():
    pytest.importorskip("pdfplumber", reason="pdfplumber not installed")
    from jobapplier.resume_parser.extractors.factory import get_extractor
    with pytest.raises(UnsupportedFormatError):
        get_extractor(Path("resume.txt"))


# O parser não depende mais de SDK de provedor: recebe um client injetado, então
# estes testes rodam sempre. Antes usavam importorskip("google.generativeai") —
# o SDK legado, que o projeto nunca instalou (usa google-genai / google.genai) —
# e por isso eram silenciosamente pulados.

def test_llm_parser_calls_client():
    from jobapplier.resume_parser.parsers import LLMResumeParser

    mock_client = MagicMock()
    mock_client.generate_json.return_value = SAMPLE_RESUME_JSON

    parser = LLMResumeParser(client=mock_client)
    result = parser.parse("Some resume text")

    assert result.nome == "Ricardo Inoue"
    mock_client.generate_json.assert_called_once()


def test_llm_parser_raises_on_invalid_json():
    from jobapplier.resume_parser.parsers import LLMResumeParser

    mock_client = MagicMock()
    mock_client.generate_json.side_effect = json.JSONDecodeError("test", "", 0)

    parser = LLMResumeParser(client=mock_client)
    with pytest.raises(ParseError):
        parser.parse("Some text")


def test_llm_parser_raises_on_schema_mismatch():
    from jobapplier.resume_parser.parsers import LLMResumeParser

    mock_client = MagicMock()
    mock_client.generate_json.return_value = {"campo": "inesperado"}

    parser = LLMResumeParser(client=mock_client)
    with pytest.raises(ParseError, match="schema"):
        parser.parse("Some text")


def test_llm_parser_raises_on_empty_text():
    """PDF do qual a extração não tirou texto não deve virar chamada de LLM."""
    from jobapplier.resume_parser.parsers import LLMResumeParser

    mock_client = MagicMock()
    parser = LLMResumeParser(client=mock_client)
    with pytest.raises(ParseError, match="vazio"):
        parser.parse("   ")
    mock_client.generate_json.assert_not_called()


def test_alias_antigo_do_parser_ainda_importa():
    from jobapplier.resume_parser.parsers import GeminiResumeParser, LLMResumeParser

    assert GeminiResumeParser is LLMResumeParser


def test_resume_json_serialization_roundtrip():
    resume = ResumeJSON.model_validate(SAMPLE_RESUME_JSON)
    dumped = resume.model_dump()
    restored = ResumeJSON.model_validate(dumped)
    assert restored.nome == resume.nome
    assert len(restored.experiencias) == len(resume.experiencias)
