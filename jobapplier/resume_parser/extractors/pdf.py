from pathlib import Path

import pdfplumber

from jobapplier.resume_parser.exceptions import ExtractionError

from .base import BaseExtractor


class PDFExtractor(BaseExtractor):
    def __init__(self, path: Path):
        super().__init__(path)

    def extract(self) -> str:
        try:
            with pdfplumber.open(self.path) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
            return "\n\n".join(pages_text)
        except Exception as exc:
            raise ExtractionError(f"Erro ao extrair texto do PDF: {exc}") from exc
