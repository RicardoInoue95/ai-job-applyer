"""Infraestrutura de teste Playwright contra HTML local.

Por que não testar contra os sites reais: LinkedIn e Gupy exigem login, e
automatizá-los num teste queima cota de detecção e arrisca a conta. Greenhouse é
público, mas depender da rede torna o teste instável e lento.

A estratégia é em três camadas:

1. ``tests/unit/test_applicators_logic.py`` — lógica pura de decisão (o que
   responder), sem browser. Rápido, roda sempre.
2. **Aqui** — Playwright real contra HTML capturado dos formulários. Exercita
   seletores, react-select e upload de arquivo sem rede. É a camada que pega
   quebra de seletor.
3. ``@pytest.mark.live`` — smoke contra formulário público real. Nunca roda por
   padrão (``pytest -m live``), só quando algo quebrou e você precisa saber se o
   HTML de produção mudou.

Para atualizar uma fixture quando um formulário muda:

    # captura o HTML atual de um board público
    python -c "
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); p = b.new_page()
        p.goto('https://boards.greenhouse.io/<slug>/jobs/<id>')
        open('tests/e2e/fixtures/greenhouse_form.html','w',encoding='utf-8').write(p.content())
        b.close()"
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def browser():
    """Chromium headless para toda a sessão. Pula se o browser não estiver instalado."""
    playwright = pytest.importorskip("playwright.sync_api", reason="playwright não instalado")

    with playwright.sync_playwright() as pw:
        try:
            navegador = pw.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium indisponível ({exc}). Rode: playwright install chromium")
        yield navegador
        navegador.close()


@pytest.fixture
def page(browser):
    """Página isolada por teste, com a mesma viewport usada em produção."""
    contexto = browser.new_context(locale="pt-BR", viewport={"width": 1280, "height": 800})
    pagina = contexto.new_page()
    yield pagina
    contexto.close()


@pytest.fixture
def carregar_fixture(page):
    """Carrega um HTML de tests/e2e/fixtures na página e devolve a página."""

    def _carregar(nome: str):
        caminho = FIXTURES / nome
        if not caminho.exists():
            pytest.skip(f"Fixture ausente: {caminho}")
        page.set_content(caminho.read_text(encoding="utf-8"))
        return page

    return _carregar
