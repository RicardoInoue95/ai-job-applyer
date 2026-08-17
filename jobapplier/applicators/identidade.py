"""Identidade canônica de uma vaga do Greenhouse.

O parser antigo falhava em 26% do acervo, por duas causas independentes.

**Subdomínio confundido com domínio.** Ele fazia ``host.split(".")[0]``, então
``careers.airbnb.com`` virava ``careers`` — e "airbnb" estava no mapa, mas nunca
era alcançado. Mesmo efeito em ``jobs.elastic.co`` e ``careers.duolingo.com``.

**Mapa fixo de domínios.** Empresas fora da lista (sumup, elastic, duolingo)
nunca resolviam, e a lista não tem como acompanhar a cauda longa.

A correção de fundo é outra: **a identidade já está no registro**. O coletor
grava ``empresa = company_slug`` e, desde a migration 004, ``fonte_empresa_id`` e
``fonte_vaga_id``. O applicator ignorava tudo isso e re-derivava da URL por
regex — a mesma patologia do ``item["id"]`` descartado na coleta.

Ordem de resolução, do mais confiável ao mais frágil:

1. campos de identidade da própria vaga
2. URL canônica do board (``boards.greenhouse.io/<slug>/jobs/<id>``)
3. ``gh_jid`` no domínio da empresa, com slug derivado do domínio registrável

Detectar ``gh_jid`` NÃO transforma qualquer domínio em Greenhouse: o slug
derivado é um palpite e precisa ser confirmado pela API antes de qualquer ação.
"""
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

BOARD_BASE = "https://boards.greenhouse.io"

#: URL canônica do próprio board. Cobre as variantes que o Greenhouse usa:
#: boards.greenhouse.io, job-boards.greenhouse.io e os boards regionais
#: (job-boards.eu.greenhouse.io), que respondem pela mesma API.
_RE_BOARD = re.compile(
    r"(?:job-)?boards(?:\.[a-z]{2})?\.greenhouse\.io/([^/?#]+)/jobs/(\d+)"
)

#: Domínios de segundo nível que não identificam a empresa: nesses casos o slug
#: está no rótulo anterior (ex.: "empresa.com.br" → "empresa").
_SUFIXOS_COMPOSTOS = {
    "com", "co", "net", "org", "gov", "edu", "ac", "com.br", "co.uk", "com.au",
}

#: Subdomínios de carreira, descartados ao derivar o slug.
_SUBDOMINIOS_IGNORADOS = {"www", "careers", "career", "jobs", "job", "boards",
                          "apply", "hire", "hiring", "work", "talent"}

#: Empresas cujo domínio não corresponde ao slug do board.
_SLUG_POR_DOMINIO = {
    "databricks": "databricks",
    "thoughtworks": "thoughtworks",
    "datadoghq": "datadog",
    "elastic": "elastic",
    "mongodb": "mongodb",
    "duolingo": "duolingo",
    "sumup": "sumup",
    "stripe": "stripe",
    "airbnb": "airbnb",
    "asana": "asana",
}


@dataclass(frozen=True)
class IdentidadeVaga:
    """Identidade resolvida de uma vaga, com a origem da resolução.

    ``confiavel`` diz se o slug veio de dado conhecido ou de palpite sobre o
    domínio. Palpite exige confirmação pela API antes de qualquer ação.
    """

    slug: str
    job_id: str
    origem: str
    url_original: str = ""

    @property
    def confiavel(self) -> bool:
        return self.origem in ("registro", "url_canonica")

    @property
    def url_canonica(self) -> str:
        return f"{BOARD_BASE}/{self.slug}/jobs/{self.job_id}"


def _dominio_registravel(host: str) -> str:
    """Rótulo que identifica a empresa, ignorando subdomínio de carreira.

    ``careers.airbnb.com`` → ``airbnb``, não ``careers``. Era exatamente esse o
    bug: o código pegava o primeiro rótulo do host.
    """
    partes = [p for p in (host or "").lower().split(".") if p]
    if not partes:
        return ""

    # Remove sufixos públicos do fim ("com", "com.br", "co.uk").
    while len(partes) > 1 and (
        partes[-1] in _SUFIXOS_COMPOSTOS
        or ".".join(partes[-2:]) in _SUFIXOS_COMPOSTOS
    ):
        if ".".join(partes[-2:]) in _SUFIXOS_COMPOSTOS and len(partes) > 2:
            partes = partes[:-2]
        else:
            partes = partes[:-1]

    # O que sobra termina no rótulo da empresa; à esquerda ficam subdomínios.
    while len(partes) > 1 and partes[0] in _SUBDOMINIOS_IGNORADOS:
        partes = partes[1:]

    return partes[-1] if partes else ""


def _gh_jid(url: str) -> str | None:
    """Valor de ``gh_jid`` na query, tolerante a ordem e a repetição."""
    try:
        valores = parse_qs(urlparse(url).query).get("gh_jid") or []
    except ValueError:
        return None
    for v in valores:
        v = (v or "").strip()
        if v.isdigit():
            return v
    return None


def resolver(vaga=None, link: str = "") -> IdentidadeVaga | None:
    """Identidade da vaga, preferindo o dado do registro à URL.

    Aceita a vaga inteira (caminho normal) ou só um link (útil em teste e em
    reprocessamento de histórico).
    """
    link = (link or getattr(vaga, "link", "") or "").strip()

    # 1. Identidade do próprio registro — o coletor já a guardou.
    if vaga is not None:
        job_id = str(getattr(vaga, "fonte_vaga_id", "") or "").strip()
        slug = str(
            getattr(vaga, "fonte_empresa_id", "") or getattr(vaga, "empresa", "") or ""
        ).strip().lower()
        if job_id.isdigit() and slug and "/" not in slug and " " not in slug:
            return IdentidadeVaga(slug, job_id, "registro", link)

    if not link:
        return None

    # 2. URL canônica do board.
    if m := _RE_BOARD.search(link):
        return IdentidadeVaga(m.group(1), m.group(2), "url_canonica", link)

    # 3. gh_jid no domínio da empresa. O slug é palpite: `confiavel` é False e
    #    quem usa precisa confirmar pela API.
    job_id = _gh_jid(link)
    if not job_id:
        return None

    try:
        partes = urlparse(link)
    except ValueError:
        return None

    # Board de vagas é http(s). Recusar outros esquemas evita que entrada
    # estranha produza uma identidade de aparência válida.
    if partes.scheme not in ("http", "https"):
        return None

    dominio = _dominio_registravel(partes.hostname or "")
    if not dominio:
        return None

    return IdentidadeVaga(
        _SLUG_POR_DOMINIO.get(dominio, dominio), job_id, "dominio", link,
    )
