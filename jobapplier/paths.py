"""Caminhos do projeto, ancorados na raiz do repositório.

Antes, módulos espalhados construíam ``Path("data/resume.json")`` — relativo ao
diretório de trabalho. Funcionava só porque todo entry point era executado da
raiz. Qualquer script rodado de outro diretório lia (ou criava) um ``data/`` no
lugar errado, silenciosamente.

Aqui a raiz é derivada de ``__file__``, então o caminho é o mesmo
independentemente de onde o processo foi iniciado.
"""
from pathlib import Path

#: Raiz do repositório: jobapplier/paths.py -> jobapplier/ -> raiz
RAIZ = Path(__file__).resolve().parent.parent

DATA = RAIZ / "data"
CONFIG_JSON = DATA / "config.json"
RESUME_JSON = DATA / "resume.json"
RESUMES = DATA / "resumes"
COVER_LETTERS = DATA / "cover_letters"
SESSIONS = DATA / "sessions"
SCREENSHOTS = DATA / "screenshots"
LINKEDIN_SESSION = SESSIONS / "linkedin.json"

ENV = RAIZ / ".env"

__all__ = [
    "CONFIG_JSON",
    "COVER_LETTERS",
    "DATA",
    "ENV",
    "LINKEDIN_SESSION",
    "RAIZ",
    "RESUMES",
    "RESUME_JSON",
    "SCREENSHOTS",
    "SESSIONS",
]


def garantir(*caminhos: Path) -> None:
    """Cria os diretórios informados, se não existirem."""
    for c in caminhos:
        c.mkdir(parents=True, exist_ok=True)
