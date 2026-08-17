"""Coletor de vagas — Gupy (plataforma brasileira)."""
import contextlib
import logging
from datetime import datetime

import requests

from jobapplier.collectors.base import BaseCollector, CollectedJob

logger = logging.getLogger(__name__)

PORTAL_API = "https://portal.api.gupy.io/api/job"
COMPANY_API = "https://{slug}.gupy.io/api/job"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


class GupyCollector(BaseCollector):
    platform = "gupy"

    def collect(self, company_slug: str) -> list[CollectedJob]:
        """Coleta vagas de uma empresa no Gupy pelo slug."""
        url = COMPANY_API.format(slug=company_slug)
        jobs: list[CollectedJob] = []
        offset = 0
        limit = 50

        while True:
            try:
                resp = requests.get(
                    url,
                    params={"offset": offset, "limit": limit},
                    headers=HEADERS,
                    timeout=15,
                )
                if resp.status_code == 404:
                    logger.warning("Gupy slug '%s' não encontrado (404).", company_slug)
                    break
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                logger.error("Erro Gupy '%s': %s", company_slug, exc)
                break

            items = data if isinstance(data, list) else data.get("data", [])
            if not items:
                break

            for item in items:
                job_id = item.get("id", "")
                title = item.get("name", "").strip()
                if not title or not job_id:
                    continue

                link = f"https://{company_slug}.gupy.io/jobs/{job_id}"
                published_raw = item.get("publishedDate") or item.get("publishedAt")
                published = None
                if published_raw:
                    with contextlib.suppress(ValueError):
                        published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))

                jobs.append(CollectedJob(
                    titulo=title,
                    empresa=item.get("careerPageName", company_slug),
                    plataforma="gupy",
                    link=link,
                    descricao=item.get("description", ""),
                    localizacao=_extract_location(item),
                    modalidade=_extract_modality(item),
                    senioridade=None,
                    data_publicacao=published,
                    fonte_vaga_id=job_id,
                    fonte_empresa_id=company_slug,
                ))

            if len(items) < limit:
                break
            offset += limit

        return jobs

    def collect_by_search(self, keywords: list[str], max_per_keyword: int = 30) -> list[CollectedJob]:
        """Coleta vagas do portal geral Gupy por palavras-chave."""
        jobs: list[CollectedJob] = []
        seen: set[str] = set()

        for kw in keywords:
            try:
                resp = requests.get(
                    PORTAL_API,
                    params={"name": kw, "offset": 0, "limit": max_per_keyword},
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
            except Exception as exc:
                logger.warning("Gupy search '%s': %s", kw, exc)
                continue

            for item in items:
                job_id = item.get("id", "")
                title = item.get("name", "").strip()
                slug = (item.get("careerPageSlug") or item.get("companySlug") or "").strip()
                if not title or not job_id or not slug:
                    continue

                link = f"https://{slug}.gupy.io/jobs/{job_id}"
                if link in seen:
                    continue
                seen.add(link)

                published_raw = item.get("publishedDate") or item.get("publishedAt")
                published = None
                if published_raw:
                    with contextlib.suppress(ValueError):
                        published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))

                jobs.append(CollectedJob(
                    titulo=title,
                    empresa=item.get("careerPageName", slug),
                    plataforma="gupy",
                    link=link,
                    descricao=item.get("description", ""),
                    localizacao=_extract_location(item),
                    modalidade=_extract_modality(item),
                    senioridade=None,
                    data_publicacao=published,
                    fonte_vaga_id=job_id,
                    fonte_empresa_id=slug,
                ))

        logger.info("Gupy search: %d vagas únicas para %s", len(jobs), keywords)
        return jobs


def _extract_location(item: dict) -> str | None:
    city = item.get("city", "")
    state = item.get("state", "")
    country = item.get("country", "")
    parts = [p for p in [city, state, country] if p]
    return ", ".join(parts) if parts else None


def _extract_modality(item: dict) -> str | None:
    remote = item.get("isRemoteWork")
    if remote is True:
        return "remoto"
    if remote is False:
        return "presencial"
    return None
