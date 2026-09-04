"""Coletor de vagas — Gupy (plataforma brasileira).

O coletor anterior devolvia zero vagas em silêncio, e por dois motivos somados:

1. `portal.api.gupy.io/api/job` responde 404. O portal migrou para
   `employability-portal.gupy.io/api/v1/jobs`, e o parâmetro de busca virou
   `jobName` (era `name`).
2. Mesmo com o endpoint certo, cada item era descartado por exigir
   `careerPageSlug` — campo que a resposta atual não traz. Todo item caía no
   `continue`, e o log dizia "0 vagas" como se a busca não tivesse resultado.

O segundo é o mais perigoso dos dois: 404 aparece no log, campo ausente não.
Por isso `collect_by_search` agora conta e loga o que descartou e por quê — um
coletor que descarta 100% precisa gritar, não retornar lista vazia.

A API não expõe salário. Medido sobre 310 vagas de dados: 1,9% têm valor em R$
na descrição, e a maioria desses é benefício (VR, auxílio), não remuneração.
Não dá para derivar faixa de mercado daqui.
"""
import contextlib
import logging
import re
from datetime import datetime

import requests

from jobapplier.collectors.base import BaseCollector, CollectedJob

logger = logging.getLogger(__name__)

PORTAL_API = "https://employability-portal.gupy.io/api/v1/jobs"
COMPANY_API = "https://{slug}.gupy.io/api/job"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

#: Teto por palavra-chave. A API aceita `limit` maior, mas cada página é uma
#: requisição e o portal é compartilhado — não vale varrer tudo por keyword.
LIMITE_PAGINA = 100

#: `workplaceType` da Gupy → vocabulário do projeto. O coletor antigo usava o
#: booleano `isRemoteWork`, que colapsa híbrido em presencial e faz o filtro 4B
#: descartar vaga híbrida em São Paulo como se fosse presencial em outro estado.
MODALIDADE = {
    "remote": "remoto",
    "hybrid": "híbrido",
    "on-site": "presencial",
    "on_site": "presencial",
}


class GupyCollector(BaseCollector):
    platform = "gupy"

    def collect(self, company_slug: str) -> list[CollectedJob]:
        """Coleta vagas de uma empresa pelo slug do career page."""
        url = COMPANY_API.format(slug=company_slug)
        jobs: list[CollectedJob] = []
        offset, limit = 0, 50

        while True:
            try:
                resp = requests.get(
                    url, params={"offset": offset, "limit": limit},
                    headers=HEADERS, timeout=15,
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
                vaga = _para_vaga(item, slug_padrao=company_slug)
                if vaga is not None:
                    jobs.append(vaga)

            if len(items) < limit:
                break
            offset += limit

        return jobs

    def collect_by_search(self, keywords: list[str],
                          max_per_keyword: int = LIMITE_PAGINA) -> list[CollectedJob]:
        """Coleta do portal geral por palavra-chave, deduplicando por id da vaga.

        A mesma vaga aparece em várias keywords ("analista de dados" e "power bi"),
        então o dedup aqui evita gerar linhas que o banco descartaria depois.
        """
        jobs: list[CollectedJob] = []
        vistos: set[str] = set()
        descartados = 0

        for kw in keywords:
            try:
                resp = requests.get(
                    PORTAL_API,
                    params={"jobName": kw, "offset": 0,
                            "limit": min(max_per_keyword, LIMITE_PAGINA)},
                    headers=HEADERS, timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                logger.warning("Gupy busca '%s': %s", kw, exc)
                continue
            except ValueError as exc:
                # Resposta 200 com corpo que não é JSON: é o sintoma de o
                # endpoint ter mudado de novo, e precisa ser distinguível de
                # "keyword sem resultado".
                logger.error("Gupy busca '%s': resposta não é JSON (%s)", kw, exc)
                continue

            items = data.get("data", []) if isinstance(data, dict) else data
            total = (data.get("pagination") or {}).get("total") if isinstance(data, dict) else None
            logger.debug("Gupy '%s': %d itens (total informado: %s)", kw, len(items), total)

            for item in items:
                identificador = str(item.get("id") or "")
                if not identificador or identificador in vistos:
                    continue
                vaga = _para_vaga(item)
                if vaga is None:
                    descartados += 1
                    continue
                vistos.add(identificador)
                jobs.append(vaga)

        if descartados:
            # Descarte em massa foi exatamente o modo de falha anterior, e ele
            # não aparecia em lugar nenhum.
            logger.warning(
                "Gupy: %d itens descartados por falta de campo obrigatório "
                "(título, id ou link).", descartados,
            )
        logger.info("Gupy: %d vagas únicas em %d keywords.", len(jobs), len(keywords))
        return jobs


def _para_vaga(item: dict, slug_padrao: str = "") -> CollectedJob | None:
    """Converte um item da API em `CollectedJob`. `None` se faltar o essencial."""
    identificador = str(item.get("id") or "").strip()
    titulo = (item.get("name") or "").strip()
    if not identificador or not titulo:
        return None

    link = (item.get("jobUrl") or "").strip()
    if not link:
        # Só monta a URL à mão quando a API não deu uma. O link da API já vem
        # com o token de origem e é o que a Gupy espera receber de volta.
        if not slug_padrao:
            return None
        link = f"https://{slug_padrao}.gupy.io/jobs/{identificador}"

    return CollectedJob(
        titulo=titulo,
        empresa=(item.get("careerPageName") or slug_padrao or "").strip(),
        plataforma="gupy",
        link=link,
        descricao=_limpar(item.get("description") or ""),
        localizacao=_localizacao(item),
        modalidade=_modalidade(item),
        senioridade=None,   # extraída depois, pelo vocabulário, a partir do título
        data_publicacao=_publicacao(item),
        fonte_vaga_id=identificador,
        fonte_empresa_id=str(
            item.get("careerPageId") or item.get("companyId") or slug_padrao or ""
        ) or None,
    )


_TAG = re.compile(r"<[^>]+>")
_ESPACO = re.compile(r"[ \t]{2,}")


def _limpar(html: str) -> str:
    """Descrição vem com HTML. O filtro 4A casa por palavra e as tags só atrapalham."""
    if not html:
        return ""
    texto = _TAG.sub(" ", html)
    texto = (texto.replace("&nbsp;", " ").replace("&amp;", "&")
             .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return _ESPACO.sub(" ", texto).strip()


def _localizacao(item: dict) -> str | None:
    partes = [item.get("city"), item.get("state"), item.get("country")]
    partes = [str(p).strip() for p in partes if p and str(p).strip()]
    return ", ".join(partes) if partes else None


def _modalidade(item: dict) -> str | None:
    """`workplaceType` primeiro; `isRemoteWork` só como reserva.

    O booleano não distingue híbrido de presencial, e híbrido em São Paulo é
    justamente o caso que interessa.
    """
    tipo = (item.get("workplaceType") or "").strip().lower()
    if tipo in MODALIDADE:
        return MODALIDADE[tipo]
    remoto = item.get("isRemoteWork")
    if remoto is True:
        return "remoto"
    if remoto is False:
        return "presencial"
    return None


def _publicacao(item: dict) -> datetime | None:
    bruto = item.get("publishedDate") or item.get("publishedAt")
    if not bruto:
        return None
    with contextlib.suppress(ValueError, AttributeError):
        return datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    return None
