"""Módulo 14 — Candidatura via Lever.

**Preenche tudo e para no hCaptcha.** O envio é concluído por você, na sessão
assistida (`scripts/finalizar.py`), no botão real da página.

Isto contraria o que o projeto documentava. `plataformas.py` e o CLAUDE.md diziam
que o Lever era "mesma família do Greenhouse — público, sem login, **sem
CAPTCHA**", e era essa frase que o fazia parecer o melhor retorno por hora de
trabalho disponível. Medido no formulário real de
`jobs.lever.co/<slug>/<id>/apply`: há um `<div class="h-captcha">` com sitekey,
dois iframes do hCaptcha, um campo oculto `h-captcha-response` e JavaScript que
prende o botão de envio até existir token. O widget é renderizado, não é
biblioteca carregada à toa.

Então envio 100% automático aqui é impossível sem contornar o hCaptcha, o que
este projeto não faz — mesma régua do Turnstile da Gupy e do `navigator.webdriver`
(invariante 6 e a política de não evadir detecção). O que sobra, e é bastante: o
formulário inteiro preenchido, currículo anexado, e o candidato resolvendo o
desafio e clicando.

**Campos do formulário**, observados na página real (não há API de perguntas como
a do Greenhouse; o que existe são `cards[<uuid>][...]` gerados por vaga):

    resume            file, o PDF
    name              obrigatório
    email             obrigatório
    phone             obrigatório
    location          obrigatório, com autocomplete que preenche `selectedLocation`
    org               obrigatório, empregador atual
    urls[LinkedIn]    urls[GitHub], urls[Portfolio], urls[Other]
    pronouns          checkboxes — SENSÍVEL, nunca preenchido
    cards[uuid][...]  perguntas customizadas da vaga
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from jobapplier.applicators.base import (
    AGUARDANDO_VERIFICACAO,
    ENVIADA_CONFIRMADA,
    FALHA_AUTOMACAO,
    REVISAO_MANUAL,
    capturar_falha,
    resultado,
)

logger = logging.getLogger(__name__)

#: `jobs.lever.co/<slug>/<id>` ou `.../<id>/apply`. O id é um uuid.
_LINK = re.compile(
    r"jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{36})", re.IGNORECASE)

#: O widget que prova que só um humano passa daqui.
_SELETORES_CAPTCHA = (
    "iframe[src*='hcaptcha']",
    ".h-captcha",
    "iframe[src*='recaptcha']",
    ".g-recaptcha",
)

#: Campos que o candidato preenche uma vez e valem para toda vaga.
_CAMPOS_BASE = ("name", "email", "phone", "location", "org")


def extrair_identidade(link: str) -> tuple[str, str] | None:
    """(slug, id) a partir do link, ou None. Aceita a URL da vaga e a de apply."""
    m = _LINK.search(link or "")
    return (m.group(1), m.group(2)) if m else None


def _preencher(page, seletor: str, valor: str) -> bool:
    """Escreve num campo. Devolve se conseguiu — silêncio aqui vira campo vazio."""
    if not valor:
        return False
    try:
        campo = page.query_selector(seletor)
        if campo is None:
            return False
        campo.fill(str(valor))
        return True
    except Exception as exc:
        logger.debug("Campo %s não preenchido: %s", seletor, exc)
        return False


def _preencher_local(page, localizacao: str) -> bool:
    """A localização tem autocomplete: digitar não basta.

    O Lever guarda o valor escolhido num `selectedLocation` oculto, e o envio
    reclama se ele ficar vazio. Digitar, esperar a lista e clicar na primeira
    sugestão é o que preenche os dois.
    """
    if not _preencher(page, "input[name='location']", localizacao):
        return False
    try:
        page.wait_for_timeout(1200)
        sugestao = page.query_selector(
            ".dropdown-location .dropdown-location-option, "
            "[class*='dropdown'] [class*='option']")
        if sugestao is not None:
            sugestao.click()
            page.wait_for_timeout(400)
    except Exception as exc:
        logger.debug("Autocomplete de local não resolveu: %s", exc)
    escolhido = page.query_selector("input[name='selectedLocation']")
    return bool(escolhido and (escolhido.get_attribute("value") or "").strip())


def perguntas_do_formulario(page) -> list[str]:
    """Perguntas customizadas da vaga (`cards[...]`) que a automação não responde.

    Diferente do Greenhouse, o Lever não expõe as perguntas por API — só existem
    no HTML da página de apply. Sem uma tabela de respostas, cada uma vira
    pergunta manual, e listá-las é o que permite ao candidato saber o que o
    espera antes de abrir o link.
    """
    from jobapplier.agents import respostas

    vistas: list[str] = []
    for campo in page.query_selector_all("[name^='cards[']"):
        try:
            if (campo.get_attribute("type") or "") == "hidden":
                continue
            rotulo = (campo.get_attribute("aria-label")
                      or campo.evaluate(
                          "e => (e.closest('li,fieldset,div')?.innerText || '')")
                      or "").strip().split("\n")[0][:120]
        except Exception:
            continue
        if rotulo and rotulo not in vistas:
            vistas.append(rotulo)

    # Pronomes e afins nunca são preenchidos, mas também não são "pergunta que
    # falta responder": são recusa deliberada. Ficam de fora da lista para não
    # inflar a contagem de bloqueio.
    return [q for q in vistas
            if respostas.classificar(q) is not respostas.Classe.SENSIVEL]


def _tem_captcha(page) -> bool:
    for seletor in _SELETORES_CAPTCHA:
        try:
            if page.query_selector(seletor) is not None:
                return True
        except Exception:
            continue
    return False


def apply(vaga, resume: dict, pdf_path: Path, cover_letter: str | None,
          visivel: bool = False, ao_verificar=None) -> dict:
    """Preenche o formulário do Lever. Não submete: o hCaptcha é seu.

    `visivel` e `ao_verificar` seguem o mesmo contrato do Greenhouse, para a
    sessão assistida funcionar igual nas duas plataformas.
    """
    from playwright.sync_api import sync_playwright

    identidade = extrair_identidade(getattr(vaga, "link", "") or "")
    if identidade is None:
        return resultado(FALHA_AUTOMACAO,
                         f"link não parece do Lever: {getattr(vaga, 'link', '')!r}")
    slug, job_id = identidade
    url = f"https://jobs.lever.co/{slug}/{job_id}/apply"

    experiencias = resume.get("experiencias") or []
    empresa_atual = experiencias[0].get("empresa", "") if experiencias else ""
    perguntas_manuais: list[str] = []
    evidencias: list = []

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=not visivel, slow_mo=80)
        page = navegador.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            if page.query_selector("input[name='name']") is None:
                evidencias = capturar_falha(page, "lever", getattr(vaga, "id", "?"))
                return resultado(
                    FALHA_AUTOMACAO,
                    "formulário não carregou (vaga encerrada ou layout mudou)",
                    evidencias=evidencias)

            _preencher(page, "input[name='name']", resume.get("nome", ""))
            _preencher(page, "input[name='email']", resume.get("email", ""))
            _preencher(page, "input[name='phone']", resume.get("telefone", ""))
            _preencher(page, "input[name='org']", empresa_atual)
            _preencher(page, "input[name='urls[LinkedIn]']", resume.get("linkedin", ""))
            _preencher(page, "input[name='urls[GitHub]']", resume.get("github") or "")
            if not _preencher_local(page, resume.get("localizacao", "")):
                perguntas_manuais.append("Localização (o autocomplete não resolveu)")

            try:
                page.set_input_files("input[type=file]", str(pdf_path))
                page.wait_for_timeout(2500)
            except Exception as exc:
                evidencias = capturar_falha(page, "lever", getattr(vaga, "id", "?"))
                return resultado(FALHA_AUTOMACAO,
                                 f"currículo não anexado: {exc}",
                                 evidencias=evidencias)

            perguntas_manuais += perguntas_do_formulario(page)

            if not _tem_captcha(page):
                # O captcha some do formulário? Ótimo — mas não é o que foi
                # medido, e assumir que sumiu levaria a marcar como enviada uma
                # candidatura que ficou na tela. Revisão manual.
                evidencias = capturar_falha(page, "lever", getattr(vaga, "id", "?"))
                return resultado(
                    REVISAO_MANUAL,
                    "formulário preenchido e sem hCaptcha na página — confira e "
                    "envie: o envio automático nunca foi validado sem o desafio",
                    perguntas_manuais=perguntas_manuais, evidencias=evidencias)

            if ao_verificar is not None and ao_verificar(page):
                return resultado(
                    ENVIADA_CONFIRMADA,
                    "enviada na sessão assistida, com confirmação na página",
                    perguntas_manuais=perguntas_manuais)

            logger.info("Lever: formulário de %s pronto, aguardando hCaptcha.", slug)
            return resultado(
                AGUARDANDO_VERIFICACAO,
                "formulário preenchido; o Lever exige hCaptcha para submeter — "
                "finalize em `scripts/finalizar.py`",
                perguntas_manuais=perguntas_manuais)
        finally:
            navegador.close()
