from pathlib import Path

from jobapplier.resume_parser.exceptions import UnsupportedFormatError

from .base import BaseExtractor
from .docx import DOCXExtractor
from .pdf import PDFExtractor

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def get_extractor(path: Path) -> BaseExtractor:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return PDFExtractor(path)
    if ext == ".docx":
        return DOCXExtractor(path)
    raise UnsupportedFormatError(
        f"Formato não suportado: {ext}. Use PDF ou DOCX."
    )
