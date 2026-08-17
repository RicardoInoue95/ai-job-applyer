import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CollectedJob:
    titulo: str
    empresa: str
    plataforma: str
    link: str
    descricao: str = ""
    localizacao: str | None = None
    modalidade: str | None = None
    senioridade: str | None = None
    salario: str | None = None
    data_publicacao: datetime | None = None
    hash: str = field(default="", init=False)

    def __post_init__(self):
        self.hash = hashlib.sha256(
            f"{self.titulo}{self.empresa}{self.link}".encode("utf-8")
        ).hexdigest()


class BaseCollector(ABC):
    platform: str = ""

    @abstractmethod
    def collect(self, company_slug: str) -> list[CollectedJob]:
        pass

    def collect_all(self, company_slugs: list[str]) -> list[CollectedJob]:
        all_jobs: list[CollectedJob] = []
        for slug in company_slugs:
            try:
                jobs = self.collect(slug)
                logger.info(
                    "[%s] %s: %d vagas encontradas", self.platform, slug, len(jobs)
                )
                all_jobs.extend(jobs)
            except Exception as exc:
                logger.error("[%s] %s: erro — %s", self.platform, slug, exc)
        return all_jobs
