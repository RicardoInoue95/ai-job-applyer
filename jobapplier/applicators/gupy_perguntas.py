"""Descoberta das perguntas de triagem da Gupy, sem login.

Eu havia concluído que era impossível: clicar em "Candidatar-se" redireciona
para `/candidates/signin`, então o **formulário** está atrás do login. Estava
errado — o formulário está, os **dados** não. A página pública é Next.js e
embute o payload inteiro em `__NEXT_DATA__`, incluindo `job.questionForm` com
título, tipo, opções, obrigatoriedade e a flag `disqualifying`.

Medido em 20 vagas de dados: 1 traz `questionForm` preenchido, 19 trazem `null`.
E `null` aqui é informação, não falha — significa que a vaga **não configurou
formulário customizado**, e o candidato se inscreve com o perfil que já tem na
Gupy. Por isso o status devolvido nesse caso é SUCESSO com lista vazia, não
FALHA_LEITURA: tratar "sem perguntas" como "não consegui ler" faria o cartão
pedir atenção humana em 95% das vagas sem motivo.

Não há credencial, cookie ou controle de acesso envolvido: é o mesmo HTML que o
navegador de qualquer visitante recebe.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from jobapplier.applicators.descoberta import (
    Descoberta,
    Pergunta,
    StatusDescoberta,
)

logger = logging.getLogger(__name__)

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)

#: Tipo da Gupy → vocabulário do projeto, o mesmo que o Greenhouse usa. Sem essa
#: tradução, `_auto_answer` receberia "SELECT" onde espera
#: "multi_value_single_select" e não responderia nada.
TIPOS = {
    "SELECT": "multi_value_single_select",
    "MULTISELECT": "multi_value_multi_select",
    "TEXT": "input_text",
    "TEXTAREA": "textarea",
    "NUMBER": "input_text",
    "DATE": "input_text",
    "BOOLEAN": "multi_value_single_select",
    "FILE": "input_file",
}


def descobrir_perguntas(link: str, timeout: int = 20) -> Descoberta:
    """Perguntas de triagem da vaga a partir da página pública.

    `SUCESSO` com lista vazia significa "esta vaga não tem pergunta extra" —
    desfecho comum e desejável, não erro.
    """
    if not link:
        return Descoberta(StatusDescoberta.RESPOSTA_INVALIDA,
                          detalhe="link vazio")

    try:
        resposta = requests.get(link, headers=CABECALHOS, timeout=timeout)
    except requests.RequestException as exc:
        return Descoberta(StatusDescoberta.FALHA_TEMPORARIA,
                          detalhe=f"{type(exc).__name__}: {exc}")

    if resposta.status_code == 404:
        return Descoberta(StatusDescoberta.VAGA_NAO_ENCONTRADA,
                          http_status=404)
    if resposta.status_code >= 500:
        return Descoberta(StatusDescoberta.FALHA_TEMPORARIA,
                          http_status=resposta.status_code)
    if resposta.status_code != 200:
        return Descoberta(StatusDescoberta.RESPOSTA_INVALIDA,
                          http_status=resposta.status_code)

    dados = _extrair_next_data(resposta.text)
    if dados is None:
        # Página sem `__NEXT_DATA__` é sinal de que a Gupy trocou o framework
        # ou serviu uma página de erro com 200. Precisa ser distinguível de
        # "vaga sem perguntas", senão a mudança passa despercebida.
        return Descoberta(
            StatusDescoberta.RESPOSTA_INVALIDA,
            http_status=200,
            detalhe="__NEXT_DATA__ ausente — a estrutura da página mudou",
        )

    vaga = (dados.get("props", {}).get("pageProps", {}).get("job") or {})
    if not vaga:
        return Descoberta(StatusDescoberta.RESPOSTA_INVALIDA, http_status=200,
                          detalhe="payload sem 'job'")

    if str(vaga.get("status", "")).lower() in ("closed", "canceled", "expired"):
        return Descoberta(StatusDescoberta.VAGA_ENCERRADA, http_status=200)

    formulario = vaga.get("questionForm") or {}
    brutas = formulario.get("questions") or []

    perguntas = [p for p in (_converter(q) for q in brutas) if p is not None]
    logger.debug("Gupy: %d pergunta(s) em %s", len(perguntas), link[:60])
    return Descoberta(StatusDescoberta.SUCESSO, perguntas=perguntas,
                      http_status=200)


def _extrair_next_data(html: str) -> dict | None:
    achado = _NEXT_DATA.search(html or "")
    if not achado:
        return None
    try:
        return json.loads(achado.group(1))
    except json.JSONDecodeError as exc:
        logger.warning("__NEXT_DATA__ ilegível: %s", exc)
        return None


def _converter(bruta: dict) -> Pergunta | None:
    """Pergunta da Gupy → contrato do projeto. `None` se não der para usar."""
    if not isinstance(bruta, dict):
        return None
    titulo = str(bruta.get("title") or "").strip()
    if not titulo:
        return None

    tipo_gupy = str(bruta.get("type") or "").upper()
    opcoes = [
        {"label": str(o.get("label", "")).strip(), "value": str(o.get("label", "")).strip()}
        for o in (bruta.get("options") or [])
        if isinstance(o, dict) and str(o.get("label", "")).strip()
    ]

    return Pergunta(
        label=titulo,
        tipo=TIPOS.get(tipo_gupy, "input_text"),
        obrigatoria=bool(bruta.get("required")),
        opcoes=opcoes,
        nome_campo=str(bruta.get("questionId") or bruta.get("customFieldId") or ""),
    )


def eliminatorias(descoberta: Descoberta, html_ou_dados: str = "") -> list[str]:
    """Rótulos das perguntas marcadas como `disqualifying` pela própria vaga.

    A Gupy declara quais respostas eliminam o candidato automaticamente. Isso
    merece destaque no cartão: errar uma dessas não é "resposta fraca", é
    descarte imediato, e vale mais a atenção humana do que dez opcionais.
    """
    if not html_ou_dados:
        return []
    dados = _extrair_next_data(html_ou_dados)
    if dados is None:
        return []
    vaga = dados.get("props", {}).get("pageProps", {}).get("job") or {}
    perguntas = (vaga.get("questionForm") or {}).get("questions") or []
    return [
        str(q.get("title", "")).strip()
        for q in perguntas
        if isinstance(q, dict) and q.get("disqualifying")
    ]
