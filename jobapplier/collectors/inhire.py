"""Coletor de vagas — inhire (ATS brasileiro).

Uma requisição por empresa devolve a lista inteira:

    GET https://api.inhire.app/job-posts/public/pages
        x-tenant: <slug da empresa>

Sem autenticação e sem paginação — 126 vagas de uma empresa vieram numa resposta
só. O `x-tenant` não é credencial: é o identificador público do career page, o
mesmo que aparece em `https://<slug>.inhire.app/vagas`.

A lista é magra de propósito (`displayName`, `jobId`, `workplaceType`,
`location`), então a descrição exige uma chamada por vaga em
`/job-posts/public/pages/<jobId>`. Isso tem custo, e por isso é limitado: vaga
sem descrição não sobrevive ao filtro 4A, mas abrir 126 páginas por empresa para
descobrir que 120 são de outra área é desperdício. O filtro por título vem
primeiro, e só o que passa é detalhado.

Descoberto lendo as chamadas de rede da página pública. Nenhum controle de acesso
é contornado: é o mesmo endpoint que o navegador de qualquer visitante usa.
"""
import logging
import re
from datetime import datetime

import requests

from jobapplier.collectors.base import BaseCollector, CollectedJob

logger = logging.getLogger(__name__)

API = "https://api.inhire.app/job-posts/public"
CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

#: `workplaceType` da inhire → vocabulário do projeto.
MODALIDADE = {
    "remote": "remoto",
    "hybrid": "híbrido",
    "on-site": "presencial",
    "onsite": "presencial",
    "office": "presencial",
}

#: Teto de páginas de detalhe por empresa. Cada uma é uma requisição, e uma
#: empresa grande tem mais de cem vagas das quais poucas interessam.
MAX_DETALHES = 30


class InhireCollector(BaseCollector):
    platform = "inhire"

    def collect(self, company_slug: str) -> list[CollectedJob]:
        """Coleta as vagas publicadas de uma empresa pelo slug do career page."""
        try:
            resposta = requests.get(
                f"{API}/pages",
                headers={**CABECALHOS, "x-tenant": company_slug},
                timeout=20,
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except requests.RequestException as exc:
            logger.warning("inhire '%s': %s", company_slug, exc)
            return []
        except ValueError as exc:
            # 200 com corpo que não é JSON é o sintoma de o endpoint ter mudado,
            # e precisa ser distinguível de "empresa sem vagas".
            logger.error("inhire '%s': resposta não é JSON (%s)", company_slug, exc)
            return []

        empresa = dados.get("tenantName") or company_slug
        brutas = [
            v for v in (dados.get("jobsPage") or [])
            if str(v.get("status", "")).lower() == "published"
        ]
        if not brutas:
            logger.info("inhire '%s': nenhuma vaga publicada.", company_slug)
            return []

        vagas = [
            v for v in (_para_vaga(b, empresa, company_slug) for b in brutas)
            if v is not None
        ]
        logger.info("inhire '%s': %d vaga(s) publicada(s).", company_slug, len(vagas))
        return vagas

    def detalhar(self, vagas: list[CollectedJob], slug: str,
                 limite: int = MAX_DETALHES) -> int:
        """Busca a descrição das vagas que ainda não têm. Uma requisição cada.

        Chamado **depois** de filtrar por título: sem descrição a vaga não passa
        no 4A, mas abrir cento e vinte páginas para descobrir que quase todas são
        de outra área gasta rede à toa.
        """
        pendentes = [v for v in vagas if not v.descricao][:limite]
        preenchidas = 0

        for vaga in pendentes:
            try:
                r = requests.get(
                    f"{API}/pages/{vaga.fonte_vaga_id}",
                    headers={**CABECALHOS, "x-tenant": slug}, timeout=15,
                )
                if r.status_code != 200:
                    continue
                descricao = _limpar(r.json().get("description") or "")
            except (requests.RequestException, ValueError) as exc:
                logger.debug("inhire detalhe %s: %s", vaga.fonte_vaga_id[:12], exc)
                continue

            if descricao:
                vaga.descricao = descricao[:20000]
                preenchidas += 1

        if pendentes:
            logger.info("inhire '%s': %d de %d descrições obtidas.",
                        slug, preenchidas, len(pendentes))
        return preenchidas


def _para_vaga(bruta: dict, empresa: str, slug: str) -> CollectedJob | None:
    identificador = str(bruta.get("jobId") or "").strip()
    titulo = str(bruta.get("displayName") or "").strip()
    if not identificador or not titulo:
        return None

    return CollectedJob(
        titulo=titulo,
        empresa=empresa,
        plataforma="inhire",
        link=f"https://{slug}.inhire.app/vagas/{identificador}",
        descricao="",   # preenchida por `detalhar`
        localizacao=_localizacao(bruta),
        modalidade=MODALIDADE.get(
            str(bruta.get("workplaceType") or "").strip().lower()),
        senioridade=None,
        data_publicacao=_publicacao(bruta),
        fonte_vaga_id=identificador,
        fonte_empresa_id=slug,
    )


#: `location` vem como código de país ("BR"), não como cidade. Traduzir para o
#: nome evita que a checagem geográfica leia "BR" como lugar desconhecido e
#: descarte a vaga como estrangeira.
_PAISES = {"BR": "Brasil", "US": "Estados Unidos", "PT": "Portugal",
           "MX": "México", "AR": "Argentina", "CL": "Chile", "CO": "Colômbia"}


def _localizacao(bruta: dict) -> str | None:
    partes = [bruta.get("city"), bruta.get("state")]
    pais = str(bruta.get("location") or "").strip()
    if pais:
        partes.append(_PAISES.get(pais.upper(), pais))
    limpas = [str(p).strip() for p in partes if p and str(p).strip()]
    return ", ".join(limpas) if limpas else None


def _publicacao(bruta: dict) -> datetime | None:
    cru = bruta.get("publishedAt") or bruta.get("createdAt")
    if not cru:
        return None
    try:
        return datetime.fromisoformat(str(cru).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


_TAG = re.compile(r"<[^>]+>")
_ESPACO = re.compile(r"[ \t]{2,}")
_ENTIDADES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&aacute;": "á", "&eacute;": "é", "&iacute;": "í", "&oacute;": "ó",
    "&uacute;": "ú", "&atilde;": "ã", "&otilde;": "õ", "&ccedil;": "ç",
    "&acirc;": "â", "&ecirc;": "ê", "&ocirc;": "ô", "&agrave;": "à",
}


def _limpar(html: str) -> str:
    """HTML → texto. A inhire devolve entidades nomeadas em português.

    Sem traduzi-las, "gest&atilde;o" não casa com "gestão" no filtro 4A, e o
    vocabulário perde termos que estão lá.
    """
    if not html:
        return ""
    texto = _TAG.sub(" ", html)
    for entidade, char in _ENTIDADES.items():
        texto = texto.replace(entidade, char)
    return _ESPACO.sub(" ", texto).strip()
