import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

from .base import BaseCollector, CollectedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

# Empresas conhecidas que usam Greenhouse — coleta automática sem configuração
DEFAULT_SLUGS: list[str] = [
    # ── Fintechs / Bancos BR ─────────────────────────────────────────────
    "nubank", "xpinc", "creditas", "stone", "neon", "cloudwalk", "pismo",
    "dock", "cora", "matera", "meliuz", "warren", "c6bank", "picpay",
    "pagseguro", "getnet", "cielo", "ebanx", "remessa-online",
    # ── PropTech / E-commerce / Marketplace BR ───────────────────────────
    "quintoandar", "loft", "luizalabs", "olist", "loggi", "getninjas",
    "enjoei", "infracommerce", "magazineluiza",
    # ── SaaS / Tech BR ───────────────────────────────────────────────────
    "vtex", "hotmart", "contaazul", "rdstation", "totvs", "linx",
    "neoway", "zupinnovation", "take", "blip", "benvo",
    # ── Healthtech / EdTech BR ───────────────────────────────────────────
    "wellhub", "gympass", "conexa-saude", "alice",
    "descomplica", "kroton", "cogna",
    # ── Agro / Energia / Industria BR ────────────────────────────────────
    "raizen", "embraer", "totvsindustrials",
    # ── Consultorias / Serviços Tech ─────────────────────────────────────
    "ciandt", "thoughtworks", "stefanini", "accenture", "deloitte",
    "capgemini", "wipro", "cognizant", "avanade",
    # ── Telecom / Mídia / Varejo BR ──────────────────────────────────────
    "globo", "uol", "americanas", "ambev",
    # ── Data & Analytics (plataformas) ───────────────────────────────────
    "databricks", "snowflake", "fivetran", "dbtlabs", "airbyte",
    "confluent", "mongodb", "elastic", "cloudflare",
    "tableau", "sigma-computing", "domo", "sisense",
    "alation", "atscale", "thoughtspot", "microstrategy",
    # ── Infraestrutura / DevOps / Cloud ──────────────────────────────────
    "hashicorp", "gitlab", "jfrog", "sonarqube",
    "datadog", "splunk", "newrelic-careers", "dynatrace", "pagerduty",
    "sumo-logic", "logdna", "sentry",
    # ── Cybersecurity ────────────────────────────────────────────────────
    "crowdstrike", "sentinelone",
    # ── Big Tech com presença BR ─────────────────────────────────────────
    "stripe", "twilio", "zendesk", "hubspot", "salesforce",
    # ── Startups internacionais presença BR ──────────────────────────────
    "ifood", "rappi", "uber", "cabify", "99taxis",
    "airbnb", "booking-com", "expedia",
    # ── Fintechs internacionais ──────────────────────────────────────────
    "brex", "rippling", "adyen", "klarna", "wise", "remitly",
    "checkout-com", "marqeta", "affirm", "plaid",
    # ── SaaS internacionais ──────────────────────────────────────────────
    "asana", "atlassian", "monday-com", "clickup",
    "airtable", "miro", "figma", "loom",
    "zapier", "segment", "amplitude", "mixpanel",
    "intercom", "freshworks", "drift", "outreach",
    "braze", "klaviyo", "iterable", "sendbird",
    # ── IA / ML ──────────────────────────────────────────────────────────
    "scale-ai", "weights-biases", "labelbox", "snorkelai",
    "cohere", "huggingface",
    # ── E-commerce internacional ─────────────────────────────────────────
    "shopify", "nuvemshop", "linx-commerce",
    # ── Gaming / Entertainment ───────────────────────────────────────────
    "wildlifestudios", "wildlife-studios", "nuuvem",
    # ── HR Tech ──────────────────────────────────────────────────────────
    "gupy", "solides", "jobscore",
    # ── Logística / Mobilidade ───────────────────────────────────────────
    "movile", "buser", "flixbus",
]


class GreenhouseCollector(BaseCollector):
    platform = "greenhouse"

    def collect(self, company_slug: str) -> list[CollectedJob]:
        url = f"{BASE_URL}/{company_slug}/jobs"
        try:
            response = requests.get(
                url,
                params={"content": "true"},
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0"},
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Erro de conexão com Greenhouse ({company_slug}): {exc}") from exc

        if response.status_code == 404:
            logger.debug("Greenhouse: empresa '%s' não encontrada (404).", company_slug)
            return []
        if response.status_code != 200:
            logger.debug("Greenhouse: '%s' retornou %s.", company_slug, response.status_code)
            return []

        jobs = []
        for item in response.json().get("jobs", []):
            location = item.get("location", {})
            location_name = location.get("name") if isinstance(location, dict) else None

            pub_date = None
            if item.get("updated_at"):
                with contextlib.suppress(ValueError):
                    pub_date = datetime.fromisoformat(
                        item["updated_at"].replace("Z", "+00:00")
                    )

            job = CollectedJob(
                titulo=item.get("title", "").strip(),
                empresa=company_slug,
                plataforma="greenhouse",
                localizacao=location_name,
                descricao=self._strip_html(item.get("content", "")),
                link=item.get("absolute_url", ""),
                data_publicacao=pub_date,
            )
            jobs.append(job)

        return jobs

    def collect_all(self, company_slugs: list[str] | None = None, max_workers: int = 12) -> list[CollectedJob]:
        """Coleta vagas em paralelo. Se company_slugs for None/vazio, usa DEFAULT_SLUGS."""
        slugs = company_slugs if company_slugs else DEFAULT_SLUGS
        all_jobs: list[CollectedJob] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self.collect, slug): slug for slug in slugs}
            for future in as_completed(futures):
                slug = futures[future]
                try:
                    jobs = future.result()
                    if jobs:
                        logger.info("[greenhouse] %s: %d vagas", slug, len(jobs))
                    all_jobs.extend(jobs)
                except Exception as exc:
                    logger.debug("[greenhouse] %s: erro — %s", slug, exc)

        logger.info("[greenhouse] Total: %d vagas de %d empresas", len(all_jobs), len(slugs))
        return all_jobs

    @staticmethod
    def _strip_html(html: str) -> str:
        if not html:
            return ""
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
