"""Módulo — LinkedIn Easy Apply via Playwright (Phase 4)."""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_PATH = Path("data/sessions/linkedin.json")

# O limite diário mora em safety/guard.py (DEFAULT_LIMITES) e é verificado pelo
# orquestrador ANTES de chegar aqui — antes de gastar token Gemini ou abrir
# browser. Havia uma constante MAX_DAILY_APPLICATIONS = 10 neste arquivo que
# nunca era consultada por ninguém.


# ── Session management ────────────────────────────────────────────────────────

def has_session() -> bool:
    return SESSION_PATH.exists() and SESSION_PATH.stat().st_size > 100


BLOCKED_MSG = "NEEDS_VISIBLE_BROWSER"


def login_and_save_session(email: str, password: str, headless: bool = True) -> tuple[bool, str]:
    """
    Faz login no LinkedIn e salva a sessão. Retorna (ok, mensagem).
    Quando headless=True falha por detecção de bot, retorna (False, BLOCKED_MSG).
    Quando headless=False, abre browser visível e aguarda o usuário completar o login.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            # Tenta Chrome instalado primeiro (menos detectável que Chromium empacotado)
            launch_kwargs = dict(
                headless=headless,
                slow_mo=150,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            try:
                browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                browser = pw.chromium.launch(**launch_kwargs)

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )
            # Remove propriedade webdriver que delata automação
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()

            if not headless:
                # Modo visível: abre a página e deixa o usuário fazer login manualmente
                page.goto("https://www.linkedin.com/login", timeout=30000, wait_until="domcontentloaded")
                # Preenche os campos para facilitar, mas o usuário pode corrigir
                try:
                    page.wait_for_selector("#username, input[name='session_key']", timeout=8000)
                    page.fill("#username", email)
                    page.fill("#password", password)
                except PWTimeout:
                    pass
                logger.info("Browser visível aberto. Aguardando login manual (até 3 min)...")
                # Aguarda o usuário chegar no feed
                try:
                    page.wait_for_url(
                        re.compile(r"linkedin\.com/(feed|jobs|mynetwork|in/)"),
                        timeout=180000,
                    )
                except PWTimeout:
                    browser.close()
                    return False, "Timeout aguardando login manual (3 min). Tente novamente."
                context.storage_state(path=str(SESSION_PATH))
                browser.close()
                return True, "Login realizado com sucesso (browser visível)."

            # Modo headless
            page.goto("https://www.linkedin.com/login", timeout=30000, wait_until="domcontentloaded")

            # Aceita cookies se banner aparecer
            try:
                btn = page.wait_for_selector(
                    "button[action-type='ACCEPT'], button:has-text('Accept'), button:has-text('Aceitar')",
                    timeout=4000,
                )
                if btn:
                    btn.click()
                    page.wait_for_timeout(800)
            except PWTimeout:
                pass

            email_sel = "#username, input[name='session_key'], input[autocomplete='username']"
            try:
                page.wait_for_selector(email_sel, timeout=15000)
            except PWTimeout:
                browser.close()
                return False, BLOCKED_MSG

            page.fill("#username", email)
            page.wait_for_timeout(300)
            page.fill("#password", password)
            page.wait_for_timeout(300)
            page.click('button[type="submit"]')
            page.wait_for_timeout(4000)

            if any(k in page.url for k in ("checkpoint", "challenge", "verify", "security")):
                browser.close()
                return False, BLOCKED_MSG

            if any(k in page.url for k in ("feed", "/jobs", "linkedin.com/in/", "mynetwork")):
                context.storage_state(path=str(SESSION_PATH))
                browser.close()
                return True, "Login realizado com sucesso."

            error_el = page.query_selector(".form__label--error, .alert-content, [role='alert']")
            error_msg = error_el.inner_text().strip() if error_el else f"URL inesperada: {page.url}"
            browser.close()
            return False, f"Login falhou: {error_msg}"

    except Exception as exc:
        logger.error("Erro no login LinkedIn: %s", exc)
        return False, str(exc)


def check_session_valid() -> bool:
    """Verifica se a sessão salva ainda está válida."""
    if not has_session():
        return False
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()
            page.goto("https://www.linkedin.com/jobs/", timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            valid = "authwall" not in page.url and "login" not in page.url
            browser.close()
            return valid
    except Exception:
        return False


# ── Easy Apply ────────────────────────────────────────────────────────────────

def _fill_easy_apply_step(page, resume: dict, pdf_path: Path | None, cover_letter: str | None) -> bool:
    """Preenche os campos de uma etapa do Easy Apply. Retorna True se preencheu algo."""
    filled = False

    # Telefone
    phone_el = page.query_selector("input[id*='phoneNumber'], input[placeholder*='Phone'], input[placeholder*='Telefone']")
    if phone_el and phone_el.is_visible() and not phone_el.input_value():
        phone_el.fill(resume.get("telefone", ""))
        filled = True

    # Upload de currículo
    resume_upload = page.query_selector("input[type=file][name*='resume'], input[type=file][id*='resume']")
    if resume_upload and pdf_path and pdf_path.exists():
        try:
            resume_upload.set_input_files(str(pdf_path))
            page.wait_for_timeout(1500)
            filled = True
        except Exception as exc:
            logger.debug("Upload PDF LinkedIn: %s", exc)

    # Cover letter (textarea)
    if cover_letter:
        cl_area = page.query_selector("textarea[id*='cover'], textarea[placeholder*='carta'], textarea[placeholder*='cover']")
        if cl_area and cl_area.is_visible() and not cl_area.input_value():
            cl_area.fill(cover_letter[:3000])
            filled = True

    # Perguntas de triagem genéricas
    _answer_screening_questions(page, resume)

    return filled


def _answer_screening_questions(page, resume: dict):
    """Responde perguntas de triagem automáticas do Easy Apply."""
    techs = [t.lower() for t in resume.get("tecnologias", [])]
    experiencias = resume.get("experiencias", [])
    localizacao = resume.get("localizacao", "").lower()

    for field_group in page.query_selector_all(".jobs-easy-apply-form-section__grouping"):
        try:
            label_el = field_group.query_selector("label, .fb-dash-form-element__label")
            label = (label_el.inner_text() if label_el else "").lower()

            # Select / combobox
            select_el = field_group.query_selector("select")
            if select_el and select_el.is_visible():
                options = select_el.query_selector_all("option")
                option_texts = [o.inner_text().lower() for o in options]

                if any(k in label for k in ["anos", "experiência", "experience"]):
                    # ~2 anos
                    for target in ["2", "1-3", "1 a 3", "1 a 2", "2-5"]:
                        for i, txt in enumerate(option_texts):
                            if target in txt:
                                select_el.select_option(index=i)
                                break
                elif any(k in label for k in ["cidade", "city", "localidade", "location"]):
                    if "são paulo" in localizacao:
                        for i, txt in enumerate(option_texts):
                            if "são paulo" in txt or "sao paulo" in txt:
                                select_el.select_option(index=i)
                                break
                elif "sim" in option_texts or "yes" in option_texts:
                    # Default: Não/No para perguntas sensíveis
                    for i, txt in enumerate(option_texts):
                        if txt in ("não", "no", "nenhum", "nenhuma"):
                            select_el.select_option(index=i)
                            break

            # Radio buttons
            radio_yes = field_group.query_selector("input[type=radio][value='Yes']")
            radio_no = field_group.query_selector("input[type=radio][value='No']")
            if radio_yes and radio_no:
                if any(k in label for k in ["python", "sql", "spark", "cloud", "azure", "aws"]):
                    has_skill = any(k in label for k in techs)
                    if has_skill:
                        radio_yes.check()
                    else:
                        radio_no.check()

            # Text input numérico (anos de experiência)
            text_el = field_group.query_selector("input[type=text], input[type=number]")
            if text_el and text_el.is_visible():
                if any(k in label for k in ["anos", "experiência", "years", "experience"]):
                    if not text_el.input_value():
                        text_el.fill("2")
        except Exception:
            continue


def apply(vaga, resume: dict, pdf_path: Path | None, cover_letter: str | None) -> dict:
    """
    Aplica via LinkedIn Easy Apply.
    Retorna dict: status, application_id, mensagem, perguntas_manuais
    """
    if not has_session():
        return {
            "status": "erro",
            "application_id": None,
            "mensagem": "Sessão LinkedIn não encontrada. Configure em Setup → Etapa 4.",
            "perguntas_manuais": [],
        }

    link = getattr(vaga, "link", "") or ""
    if "linkedin.com" not in link:
        return {"status": "erro", "application_id": None,
                "mensagem": f"Link não é do LinkedIn: {link}", "perguntas_manuais": []}

    logger.info("LinkedIn Easy Apply: %s", link)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context(
            storage_state=str(SESSION_PATH),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="pt-BR",
        )
        page = context.new_page()

        try:
            page.goto(link, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            if "authwall" in page.url or "login" in page.url:
                browser.close()
                return {"status": "erro", "application_id": None,
                        "mensagem": "Sessão expirada. Faça login novamente em Setup → Etapa 4.",
                        "perguntas_manuais": []}

            # Jitter de mouse/scroll antes de interagir (Módulo 9)
            from safety import guard
            guard.humanizar(page)

            # Clica no botão Easy Apply
            easy_apply_btn = (
                page.query_selector("button.jobs-apply-button[aria-label*='Easy Apply']")
                or page.query_selector("button[aria-label*='Easy Apply']")
                or page.query_selector(".jobs-apply-button")
                or page.query_selector("button:has-text('Easy Apply')")
                or page.query_selector("button:has-text('Fácil Candidatura')")
            )

            if not easy_apply_btn:
                browser.close()
                return {"status": "erro", "application_id": None,
                        "mensagem": "Botão Easy Apply não encontrado — vaga pode não ter Easy Apply.",
                        "perguntas_manuais": []}

            easy_apply_btn.click()
            page.wait_for_timeout(2000)

            # Preenche multi-step form
            max_steps = 8
            for step in range(max_steps):
                _fill_easy_apply_step(page, resume, pdf_path, cover_letter)
                page.wait_for_timeout(600)

                # Próximo / Submit
                next_btn = (
                    page.query_selector("button[aria-label='Continue to next step']")
                    or page.query_selector("button[aria-label='Submit application']")
                    or page.query_selector("button:has-text('Próxima')")
                    or page.query_selector("button:has-text('Enviar candidatura')")
                    or page.query_selector("button:has-text('Próximo')")
                    or page.query_selector("button:has-text('Submit')")
                )

                if not next_btn:
                    break

                label_text = (next_btn.get_attribute("aria-label") or next_btn.inner_text() or "").lower()

                if "submit" in label_text or "enviar" in label_text:
                    next_btn.click()
                    page.wait_for_timeout(3000)
                    # Verifica confirmação
                    content = page.content().lower()
                    success = (
                        "candidatura enviada" in content
                        or "application submitted" in content
                        or "sua candidatura foi" in content
                        or page.query_selector("[aria-label*='submitted']") is not None
                    )
                    browser.close()
                    if success:
                        logger.info("LinkedIn Easy Apply enviado com sucesso!")
                        return {"status": "enviada", "application_id": None,
                                "mensagem": "Candidatura enviada via LinkedIn Easy Apply.",
                                "perguntas_manuais": []}
                    else:
                        return {"status": "erro", "application_id": None,
                                "mensagem": "Submit clicado mas confirmação não detectada.",
                                "perguntas_manuais": []}

                next_btn.click()
                page.wait_for_timeout(1500)

            browser.close()
            return {"status": "erro", "application_id": None,
                    "mensagem": "Não foi possível completar todos os passos do Easy Apply.",
                    "perguntas_manuais": []}

        except Exception as exc:
            logger.error("Erro no LinkedIn Easy Apply: %s", exc)
            try:
                browser.close()
            except Exception:
                pass
            return {"status": "erro", "application_id": None,
                    "mensagem": f"Erro: {exc}", "perguntas_manuais": []}


# ── Coleta de vagas LinkedIn ──────────────────────────────────────────────────

def _extract_job_id(href: str) -> str:
    """Extrai o ID numérico de uma URL /jobs/view/NNNN."""
    m = re.search(r"/jobs/view/(\d+)", href)
    return m.group(1) if m else ""


def _scrape_cards(page, max_cards: int) -> list[dict]:
    """Extrai vagas dos cards. Prioriza data-occludable-job-id."""
    jobs: list[dict] = []

    cards = page.query_selector_all("[data-occludable-job-id]")
    if not cards:
        cards = page.query_selector_all("li[data-job-id]")
    if not cards:
        cards = page.query_selector_all(".job-card-container, .scaffold-layout__list-item")

    logger.info("Cards no DOM: %d", len(cards))

    for card in cards[:max_cards]:
        try:
            # ── Job ID e link ────────────────────────────────────────────────
            link = ""
            for attr in ("data-occludable-job-id", "data-job-id", "data-entity-urn"):
                val = card.get_attribute(attr) or ""
                jid = re.search(r"\d{7,}", val)
                if jid:
                    link = f"https://www.linkedin.com/jobs/view/{jid.group()}/"
                    break
            # fallback: qualquer href /jobs/view/ dentro do card
            if not link:
                a_el = card.query_selector("a[href*='/jobs/view/']")
                if a_el:
                    link = (a_el.get_attribute("href") or "").split("?")[0]
            if not link:
                continue  # sem link não tem como candidatar

            # ── Título ───────────────────────────────────────────────────────
            title = ""
            for sel in (
                ".job-card-list__title--link",
                ".job-card-list__title",
                "a[href*='/jobs/view/']",
                "[class*='title'] a",
                "[class*='title'] strong",
            ):
                el = card.query_selector(sel)
                if el:
                    title = el.inner_text().strip()
                    if not title:
                        # tenta aria-label quando inner_text vazio (card occluded)
                        title = (el.get_attribute("aria-label") or "").strip()
                    if title:
                        break

            # ── Empresa ──────────────────────────────────────────────────────
            company = ""
            for sel in (
                ".job-card-container__company-name",
                ".artdeco-entity-lockup__subtitle span",
                "[class*='company-name']",
                ".job-card-container__primary-description",
            ):
                el = card.query_selector(sel)
                if el:
                    company = el.inner_text().strip()
                    if company:
                        break

            # ── Localização ──────────────────────────────────────────────────
            loc = ""
            for sel in (
                ".job-card-container__metadata-item",
                ".artdeco-entity-lockup__caption li",
                "[class*='metadata'] li",
            ):
                el = card.query_selector(sel)
                if el:
                    loc = el.inner_text().strip()
                    if loc:
                        break

            # Cards occluded podem ter link mas não título ainda — aceita assim
            # O título ficará vazio e será preenchido ao normalizar a vaga
            jobs.append({
                "titulo": title or f"Vaga LinkedIn {link.rstrip('/').split('/')[-1]}",
                "empresa": company,
                "localizacao": loc,
                "link": link,
                "plataforma": "linkedin",
                "descricao": "",
            })

        except Exception:
            continue

    return jobs


def _scroll_list_panel(page) -> None:
    """
    Rola o painel esquerdo de resultados para forçar o render de todos os cards
    (LinkedIn usa occlusion: cards fora da viewport não têm conteúdo no DOM).
    """
    panel_sel = (
        ".jobs-search-results-list, "
        ".scaffold-layout__list, "
        ".jobs-search__results-list"
    )
    page.evaluate(f"""
        (function() {{
            const panel = document.querySelector('{panel_sel}');
            if (!panel) return;
            let pos = 0;
            const step = 350;
            const max = panel.scrollHeight;
            function tick() {{
                pos += step;
                panel.scrollTop = pos;
                if (pos < max) setTimeout(tick, 250);
            }}
            tick();
        }})();
    """)
    # Aguarda o scroll JS terminar (~250ms * (max/step) iterações)
    page.wait_for_timeout(4000)


def collect_jobs(search_queries: list[str], location: str = "São Paulo, BR",
                 max_per_query: int = 25) -> list[dict]:
    """Coleta vagas do LinkedIn usando a sessão salva."""
    if not has_session():
        logger.warning("Sessão LinkedIn não encontrada.")
        return []

    from urllib.parse import quote_plus

    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            slow_mo=60,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            storage_state=str(SESSION_PATH),
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()

        for query in search_queries:
            try:
                url = (
                    "https://www.linkedin.com/jobs/search/"
                    f"?keywords={quote_plus(query)}"
                    f"&location={quote_plus(location)}"
                    "&f_LF=f_AL"
                    "&sortBy=DD"
                    "&start=0"
                )
                logger.info("LinkedIn buscando: %s", query)
                page.goto(url, timeout=30000, wait_until="domcontentloaded")

                # Aguarda pelo menos 1 card aparecer
                try:
                    page.wait_for_selector("[data-occludable-job-id]", timeout=12000)
                except PWTimeout:
                    if "authwall" in page.url or "login" in page.url:
                        logger.warning("Sessão LinkedIn expirada.")
                        break
                    logger.warning("Query '%s': sem cards após 12s.", query)
                    continue

                # Rola painel para forçar render de todos os cards ocultos
                _scroll_list_panel(page)

                found = _scrape_cards(page, max_per_query)
                unique = [j for j in found if j["link"] not in seen_urls]
                for j in unique:
                    seen_urls.add(j["link"])
                all_jobs.extend(unique)
                logger.info("Query '%s': %d vagas (%d unicas)", query, len(found), len(unique))

            except Exception as exc:
                logger.warning("Erro LinkedIn '%s': %s", query, exc)

        browser.close()

    logger.info("LinkedIn: %d vagas coletadas no total", len(all_jobs))
    return all_jobs
