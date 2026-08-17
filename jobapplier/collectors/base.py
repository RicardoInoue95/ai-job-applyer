import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


def _sha(*partes: str) -> str:
    return hashlib.sha256("\x1f".join(partes).encode("utf-8")).hexdigest()


@dataclass
class CollectedJob:
    """Uma vaga coletada, com identidade separada de conteúdo.

    Três identificadores, com papéis distintos:

    ``fonte_vaga_id`` — o id da vaga na própria plataforma. É a identidade
    **estável**: sobrevive a republicação, a mudança de título e a parâmetro
    extra no link. Todas as três APIs devolvem isso, e o projeto vinha jogando
    fora: o Greenhouse ignorava ``item["id"]`` e depois o applicator o recuperava
    por regex do ``absolute_url``.

    ``hash`` — sha256(titulo, empresa, link). Identidade legada, mantida porque
    todas as linhas já no banco a usam. Frágil: muda se o título muda ou se o
    link ganha um parâmetro, e a mesma vaga entra de novo.

    ``content_hash`` — sha256 da descrição. Não é identidade; serve para detectar
    que o texto mudou e a normalização precisa ser refeita.
    """

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
    #: Id da vaga na plataforma de origem. Preferir sempre a este para dedup.
    fonte_vaga_id: str | None = None
    #: Id/slug da empresa na plataforma de origem.
    fonte_empresa_id: str | None = None
    hash: str = field(default="", init=False)
    content_hash: str = field(default="", init=False)

    def __post_init__(self):
        # Mantido idêntico ao original: mudar invalidaria a dedup de tudo que já
        # está no banco, e cada vaga existente entraria como nova.
        self.hash = hashlib.sha256(
            f"{self.titulo}{self.empresa}{self.link}".encode()
        ).hexdigest()
        self.content_hash = _sha(self.descricao or "")
        if self.fonte_vaga_id is not None:
            self.fonte_vaga_id = str(self.fonte_vaga_id).strip() or None
        if self.fonte_empresa_id is not None:
            self.fonte_empresa_id = str(self.fonte_empresa_id).strip() or None

    @property
    def identidade(self) -> tuple[str, str] | None:
        """(plataforma, fonte_vaga_id) — a chave de dedup preferida, ou None."""
        if not self.fonte_vaga_id:
            return None
        return (self.plataforma.lower(), self.fonte_vaga_id)


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
