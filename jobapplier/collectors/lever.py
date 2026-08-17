import contextlib
import logging
import re

import requests

from jobapplier.tempo import de_timestamp

from .base import BaseCollector, CollectedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings"


class LeverCollector(BaseCollector):
    platform = "lever"

    def collect(self, company_slug: str) -> list[CollectedJob]:
        url = f"{BASE_URL}/{company_slug}"
        try:
            response = requests.get(
                url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"},
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Erro de conexão com Lever ({company_slug}): {exc}") from exc

        if response.status_code == 404:
            logger.warning("Lever: empresa '%s' não encontrada", company_slug)
            return []
        response.raise_for_status()

        jobs = []
        for item in response.json():
            categories = item.get("categories") or {}
            location = categories.get("location") or None
            commitment = categories.get("commitment") or None

            pub_date = None
            if item.get("createdAt"):
                with contextlib.suppress(ValueError, OSError):
                    pub_date = de_timestamp(item["createdAt"] / 1000)

            description_plain = item.get("descriptionPlain") or item.get("description") or ""
            description_plain = self._strip_html(description_plain)

            job = CollectedJob(
                titulo=item.get("text", "").strip(),
                empresa=company_slug,
                plataforma="lever",
                localizacao=location,
                modalidade=commitment,
                descricao=description_plain,
                link=item.get("hostedUrl", ""),
                fonte_vaga_id=item.get("id"),
                fonte_empresa_id=company_slug,
                data_publicacao=pub_date,
            )
            jobs.append(job)

        return jobs

    @staticmethod
    def _strip_html(html: str) -> str:
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
