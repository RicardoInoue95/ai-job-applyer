"""Módulo — Gupy candidatura via Playwright (Phase 5)."""
import contextlib
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

GUPY_JOB_RE = re.compile(r"https?://([^.]+)\.gupy\.io/jobs/(\d+)")


def _parse_link(link: str) -> tuple[str, str] | None:
    m = GUPY_JOB_RE.match(link)
    if not m:
        return None
    return m.group(1), m.group(2)  # (slug, job_id)


def apply(vaga, resume: dict, pdf_path: Path | None, cover_letter: str | None) -> dict:
    """Aplica para uma vaga no Gupy via Playwright. Retorna dict status."""
    link = getattr(vaga, "link", "") or ""
    parsed = _parse_link(link)
    if not parsed:
        return {
            "status": "erro",
            "application_id": None,
            "mensagem": f"Link Gupy inválido: {link}",
            "perguntas_manuais": [],
        }

    slug, job_id = parsed
    form_url = f"https://{slug}.gupy.io/jobs/{job_id}/apply"
    logger.info("Gupy Playwright: %s", form_url)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, slow_mo=80)
        context = browser.new_context(locale="pt-BR")
        page = context.new_page()

        try:
            page.goto(form_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Preenche nome
            first_name = resume.get("nome", "").split()[0] if resume.get("nome") else ""
            last_name = " ".join(resume.get("nome", "").split()[1:]) if resume.get("nome") else ""
            _fill(page, "input[name*='firstName'], input[id*='firstName'], input[placeholder*='Nome']", first_name)
            _fill(page, "input[name*='lastName'], input[id*='lastName'], input[placeholder*='Sobrenome']", last_name)
            _fill(page, "input[name*='email'], input[type='email']", resume.get("email", ""))
            _fill(page, "input[name*='phone'], input[name*='cellphone'], input[placeholder*='Telefone']", resume.get("telefone", ""))

            # Upload de currículo
            if pdf_path and pdf_path.exists():
                resume_input = page.query_selector("input[type='file']")
                if resume_input:
                    try:
                        resume_input.set_input_files(str(pdf_path))
                        page.wait_for_timeout(1500)
                    except Exception as exc:
                        logger.debug("Gupy upload PDF: %s", exc)

            # Cover letter
            if cover_letter:
                cl_area = page.query_selector("textarea")
                if cl_area and cl_area.is_visible():
                    with contextlib.suppress(Exception):
                        cl_area.fill(cover_letter[:3000])

            # LinkedIn URL
            _fill(page, "input[name*='linkedin']", resume.get("linkedin", ""))

            page.wait_for_timeout(500)

            # Perguntas de triagem
            pending = _answer_gupy_questions(page, resume)

            if pending:
                browser.close()
                return {
                    "status": "perguntas_pendentes",
                    "application_id": None,
                    "mensagem": "Perguntas sem resposta automática no formulário Gupy.",
                    "perguntas_manuais": pending,
                }

            # Submete
            submit_btn = (
                page.query_selector("button[type='submit']")
                or page.query_selector("button:has-text('Enviar')")
                or page.query_selector("button:has-text('Candidatar')")
                or page.query_selector("button:has-text('Submit')")
            )
            if not submit_btn:
                browser.close()
                return {
                    "status": "erro",
                    "application_id": None,
                    "mensagem": "Botão de submissão não encontrado no formulário Gupy.",
                    "perguntas_manuais": [],
                }

            submit_btn.click()
            page.wait_for_timeout(4000)

            content = page.content().lower()
            success = (
                "candidatura enviada" in content
                or "obrigado" in content
                or "application submitted" in content
                or "thank you" in content
                or "/success" in page.url
                or "/confirmation" in page.url
            )

            browser.close()

            if success:
                logger.info("Gupy candidatura enviada com sucesso!")
                return {
                    "status": "enviada",
                    "application_id": None,
                    "mensagem": "Candidatura enviada via Gupy.",
                    "perguntas_manuais": [],
                }
            return {
                "status": "erro",
                "application_id": None,
                "mensagem": "Submit clicado mas confirmação Gupy não detectada.",
                "perguntas_manuais": [],
            }

        except Exception as exc:
            logger.error("Erro Gupy Playwright: %s", exc)
            with contextlib.suppress(Exception):
                browser.close()
            return {
                "status": "erro",
                "application_id": None,
                "mensagem": f"Erro: {exc}",
                "perguntas_manuais": [],
            }


def _fill(page, selector: str, value: str) -> bool:
    """Preenche o primeiro campo visível que corresponde ao seletor. Retorna True se preencheu."""
    if not value:
        return False
    try:
        for sel in selector.split(","):
            sel = sel.strip()
            el = page.query_selector(sel)
            if el and el.is_visible() and not el.input_value():
                el.fill(value)
                return True
    except Exception:
        pass
    return False


def _answer_gupy_questions(page, resume: dict) -> list[str]:
    """Responde perguntas de triagem do Gupy. Retorna lista de perguntas sem resposta."""
    pending = []

    question_groups = page.query_selector_all(
        "[data-testid*='question'], .gupy-question, .question-wrapper, fieldset"
    )
    if not question_groups:
        return []

    for group in question_groups:
        try:
            label_el = group.query_selector("label, legend, p, span")
            label = (label_el.inner_text() if label_el else "").strip().lower()
            if not label:
                continue

            # Select
            select_el = group.query_selector("select")
            if select_el and select_el.is_visible():
                options = [o.inner_text().lower() for o in select_el.query_selector_all("option")]
                if any(k in label for k in ["anos de experiência", "years of experience"]):
                    for idx, txt in enumerate(options):
                        if any(n in txt for n in ["2", "1-3", "1 a 3", "2-5"]):
                            select_el.select_option(index=idx)
                            break
                elif any(k in label for k in ["escolaridade", "graduação", "formação"]):
                    for idx, txt in enumerate(options):
                        if any(n in txt for n in ["graduação", "superior", "bacharel"]):
                            select_el.select_option(index=idx)
                            break
                continue

            # Radio / checkbox
            radios = group.query_selector_all("input[type='radio']")
            if radios:
                answered = False
                for radio in radios:
                    val = (radio.get_attribute("value") or "").lower()
                    radio_label = ""
                    try:
                        radio_label_el = page.query_selector(f"label[for='{radio.get_attribute('id')}']")
                        radio_label = (radio_label_el.inner_text() if radio_label_el else "").lower()
                    except Exception:
                        pass

                    if any(k in label for k in ["clt", "pj", "contratação"]):
                        if "clt" in val or "clt" in radio_label:
                            radio.check()
                            answered = True
                            break
                    elif any(k in label for k in ["sim", "não", "yes", "no"]):
                        if val in ("não", "no", "nao") or "não" in radio_label:
                            radio.check()
                            answered = True
                            break
                if not answered:
                    pending.append(label[:100])
                continue

            # Text input numérico (pretensão salarial, anos)
            text_el = group.query_selector("input[type='text'], input[type='number']")
            if text_el and text_el.is_visible() and not text_el.input_value():
                if any(k in label for k in ["salário", "pretensão", "salary"]):
                    text_el.fill("0")
                elif any(k in label for k in ["anos", "experience", "experiência"]):
                    text_el.fill("2")
                else:
                    pending.append(label[:100])

        except Exception:
            continue

    return pending
