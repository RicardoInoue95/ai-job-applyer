"""A vaga ainda existe? Uma pergunta HTTP por vaga, sem browser.

Amostra de 40 vagas do Greenhouse na fila: **9 estavam encerradas, 22%**. Some
as 8 da inhire, todas mortas, e o quadro é uma fila que apresenta como
oportunidade algo que já acabou. O usuário escolhe o cartão, lê o dossiê, decide
candidatar — e leva 404 no link.

É o "decisão sem informação é carimbo" do CLAUDE.md na forma mais literal, e o
mais barato de resolver: cada plataforma diz se a vaga acabou, em uma chamada.

**A direção segura é não encerrar.** `INDETERMINADA` existe para erro de rede,
resposta estranha e plataforma sem checagem, e nunca vira `encerrada`: descartar
vaga viva por causa de um timeout é pior que manter uma morta na fila mais um
ciclo. O erro que este módulo pode cometer tem de ser sempre o de deixar passar.
"""
from __future__ import annotations

import json
import logging
import re
from enum import StrEnum

import requests

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 15

#: Marcadores extraídos de páginas reais.
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_LEVER = re.compile(r"jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{36})", re.I)


class Vigencia(StrEnum):
    ABERTA = "aberta"
    ENCERRADA = "encerrada"
    #: Não deu para saber. Nunca encerra nada.
    INDETERMINADA = "indeterminada"


def checar(vaga) -> tuple[Vigencia, str]:
    """(vigência, motivo) de uma vaga. Nunca levanta."""
    plataforma = (getattr(vaga, "plataforma", "") or "").lower()
    checador = _CHECADORES.get(plataforma)
    if checador is None:
        return Vigencia.INDETERMINADA, f"sem checagem para '{plataforma}'"
    try:
        return checador(vaga)
    except Exception as exc:
        # Uma vaga problemática não pode derrubar a varredura das outras.
        return Vigencia.INDETERMINADA, f"{type(exc).__name__}: {exc}"


def _greenhouse(vaga) -> tuple[Vigencia, str]:
    """Reusa `descobrir_perguntas`, que já classifica 404, 5xx e `closed_at`.

    Uma segunda leitura do mesmo endpoint seria mais leve — não pede as
    perguntas — e seria uma cópia da mesma lógica de classificação. Cópia
    diverge; o peso extra é uma query string.
    """
    from jobapplier.applicators.descoberta import StatusDescoberta
    from jobapplier.applicators.greenhouse import descobrir_perguntas
    from jobapplier.applicators.identidade import resolver

    ident = resolver(vaga)
    if ident is None or not ident.slug:
        return Vigencia.INDETERMINADA, "link não resolvido"

    d = descobrir_perguntas(ident.slug, ident.job_id)
    if d.status is StatusDescoberta.VAGA_NAO_ENCONTRADA:
        return Vigencia.ENCERRADA, "404 no board"
    if d.status is StatusDescoberta.VAGA_ENCERRADA:
        return Vigencia.ENCERRADA, "board marca como encerrada"
    if d.status is StatusDescoberta.SUCESSO:
        return Vigencia.ABERTA, ""
    return Vigencia.INDETERMINADA, str(d.detalhe or d.status)


def _lever(vaga) -> tuple[Vigencia, str]:
    m = _LEVER.search(getattr(vaga, "link", "") or "")
    if not m:
        return Vigencia.INDETERMINADA, "link não parece do Lever"
    r = requests.get(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}",
                     timeout=TIMEOUT, headers=_UA)
    if r.status_code == 404:
        return Vigencia.ENCERRADA, "404 na API do Lever"
    if r.status_code == 200:
        return Vigencia.ABERTA, ""
    return Vigencia.INDETERMINADA, f"HTTP {r.status_code}"


def _gupy(vaga) -> tuple[Vigencia, str]:
    """A Gupy devolve 200 mesmo para vaga encerrada.

    A palavra "encerrada" aparece no HTML de toda vaga, aberta ou não — é rótulo
    de interface, e procurá-la no texto marcaria o acervo inteiro como morto. O
    dado está em `__NEXT_DATA__ > props.pageProps.job.status`, que vale
    `published` enquanto a vaga recebe candidatura.
    """
    link = getattr(vaga, "link", "") or ""
    if not link:
        return Vigencia.INDETERMINADA, "sem link"
    r = requests.get(link, timeout=TIMEOUT, headers=_UA, allow_redirects=True)
    if r.status_code == 404:
        return Vigencia.ENCERRADA, "404 na página"
    if r.status_code != 200:
        return Vigencia.INDETERMINADA, f"HTTP {r.status_code}"

    m = _NEXT_DATA.search(r.text)
    if not m:
        return Vigencia.INDETERMINADA, "página sem __NEXT_DATA__"
    try:
        dados = json.loads(m.group(1))
    except json.JSONDecodeError:
        return Vigencia.INDETERMINADA, "__NEXT_DATA__ ilegível"

    job = ((dados.get("props") or {}).get("pageProps") or {}).get("job") or {}
    status = str(job.get("status") or "").lower()
    if not status:
        return Vigencia.INDETERMINADA, "sem campo status"
    if status == "published":
        return Vigencia.ABERTA, ""
    return Vigencia.ENCERRADA, f"status '{status}'"


def _inhire(vaga) -> tuple[Vigencia, str]:
    """A inhire lista as vagas abertas do tenant; ausente da lista é encerrada.

    Não há endpoint por vaga, então a checagem é por presença. O tenant sai do
    subdomínio do link (`radix.inhire.app`).
    """
    link = getattr(vaga, "link", "") or ""
    m = re.search(r"https?://([\w-]+)\.inhire\.app", link)
    if not m:
        return Vigencia.INDETERMINADA, "link sem tenant"
    r = requests.get("https://api.inhire.app/job-posts/public/pages",
                     headers={**_UA, "x-tenant": m.group(1)}, timeout=TIMEOUT)
    if r.status_code != 200:
        return Vigencia.INDETERMINADA, f"HTTP {r.status_code}"
    dados = r.json()
    vagas = dados if isinstance(dados, list) else (
        dados.get("data") or dados.get("items") or [])
    abertos = {str(v.get("id") or v.get("slug") or "") for v in vagas}
    identificador = link.rstrip("/").split("/")[-1]
    if identificador and identificador in abertos:
        return Vigencia.ABERTA, ""
    return Vigencia.ENCERRADA, f"ausente das {len(abertos)} vagas abertas do tenant"


#: LinkedIn fica de fora: checar exigiria a sessão salva, e cada leitura
#: automatizada gasta cota de detecção de uma conta que é a identidade
#: profissional real do usuário (invariante 6). Vaga do LinkedIn envelhece na
#: fila, e isso é menos ruim que arriscar a conta para saber.
_CHECADORES = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "gupy": _gupy,
    "inhire": _inhire,
}


def suportada(plataforma: str) -> bool:
    return (plataforma or "").lower() in _CHECADORES
