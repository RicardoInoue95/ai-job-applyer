"""Captura as páginas da UI em viewport de desktop, para revisão visual.

    python run.py                                        # em outro terminal
    .venv\\Scripts\\python.exe scripts\\ui_screenshots.py

Existe porque `HTTP 200` não prova nada: o Streamlit devolve 200 com o traceback
dentro da página, e o teste de contrato (`tests/unit/test_ui_contrato.py`) só
pega nome de coluna errado. Nenhum dos dois enxerga layout.

Duas telas foram entregues com `layout="centered"` ocupando 736 de 1600 pixels e
três expanders fechados empilhados. Passou por lint, por teste e por checagem de
HTTP — e só apareceu quando o usuário disse que parecia feito para celular.

Além da imagem, imprime a **largura ocupada pelo conteúdo**. Abaixo de ~70% do
viewport numa página de trabalho, o `layout` está errado.
"""
import contextlib
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jobapplier import paths

#: Monitor de trabalho comum. Não use viewport de celular para avaliar uma tela
#: que existe para triar 216 vagas.
VIEWPORT = {"width": 1600, "height": 900}

#: (url_path, nome do arquivo). Os url_path vêm de `st.Page` em app.py;
#: navegar pelo menu é mais fiel ao uso real que abrir a URL direto.
PAGINAS = (("dashboard", "Dashboard"), ("vagas", "Vagas"),
           ("revisar", "Revisar e aplicar"), ("candidaturas", "Candidaturas"),
           ("configuracoes", "Configurações"))

#: Configurações é seis telas atrás de um `segmented_control`: uma captura só
#: mostra "Preferências" e esconde as outras cinco. Rótulos vêm de `SECOES` em
#: `ui/pages/1_Setup.py`.
SECOES_CONFIG = ("Preferências", "Plataformas", "LinkedIn", "Currículo",
                 "Provedor de IA", "Notificações")

#: Abaixo disto, a página desperdiça a tela.
OCUPACAO_MINIMA = 0.70

_LARGURA_JS = """() => {
    const el = document.querySelector('.stMainBlockContainer')
            || document.querySelector('[data-testid="stAppViewBlockContainer"]')
            || document.querySelector('section.main');
    return el ? Math.round(el.getBoundingClientRect().width) : -1;
}"""

#: Altura real do conteúdo. `full_page=True` sozinho devolve só o viewport: quem
#: rola no Streamlit é o `.stMain`, não o documento, então `document` nunca fica
#: mais alto que a janela e a captura corta tudo abaixo da dobra.
_ALTURA_JS = """() => {
    const alvos = ['.stMain', 'section.main', '.stMainBlockContainer',
                   '[data-testid="stAppViewContainer"]',
                   '[data-testid="stSidebar"]'];
    let h = document.documentElement.scrollHeight;
    for (const s of alvos) {
        const el = document.querySelector(s);
        if (el) h = Math.max(h, el.scrollHeight);
    }
    return Math.ceil(h);
}"""

#: Teto de segurança. A lista de Vagas rende 100 cartões; sem teto a imagem
#: passa de 20.000px e nenhum visualizador abre.
ALTURA_MAXIMA = 20000

#: O cabeçalho do Streamlit é fixo e flutua sobre o conteúdo: se o container
#: ficou rolado, o título da página sai cortado na captura.
_TOPO_JS = """() => {
    window.scrollTo(0, 0);
    for (const s of ['.stMain', 'section.main',
                     '[data-testid="stSidebar"] > div']) {
        const el = document.querySelector(s);
        if (el) el.scrollTop = 0;
    }
}"""


def _ascii(rotulo: str) -> str:
    """Nome de arquivo sem acento: 'Notificações' vira 'notificacoes'."""
    sem_acento = unicodedata.normalize("NFKD", rotulo).encode(
        "ascii", "ignore").decode()
    return sem_acento.lower().replace(" ", "_")


def _capturar(pagina, arquivo) -> int:
    """Estica a janela até o conteúdo inteiro caber e salva. Devolve a altura.

    Duas passadas porque esticar re-renderiza (gráfico redimensiona, coluna
    reflui) e a altura medida na primeira passada muda.
    """
    altura = VIEWPORT["height"]
    for _ in range(2):
        medida = min(pagina.evaluate(_ALTURA_JS), ALTURA_MAXIMA)
        if medida <= altura + 8:
            break
        altura = medida
        pagina.set_viewport_size({"width": VIEWPORT["width"], "height": altura})
        pagina.wait_for_timeout(2500)

    pagina.evaluate(_TOPO_JS)
    pagina.wait_for_timeout(400)
    pagina.screenshot(path=str(arquivo), full_page=True)
    pagina.set_viewport_size(VIEWPORT)
    pagina.wait_for_timeout(1200)
    return altura


def main(porta: str = "8501") -> int:
    from playwright.sync_api import sync_playwright

    destino = paths.SCREENSHOTS / "ui"
    destino.mkdir(parents=True, exist_ok=True)

    problemas = 0
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        pagina = navegador.new_context(viewport=VIEWPORT, locale="pt-BR").new_page()

        print(f"\n  viewport {VIEWPORT['width']}x{VIEWPORT['height']}\n")
        primeira = True
        for rota, rotulo in PAGINAS:
            try:
                if primeira:
                    pagina.goto(f"http://localhost:{porta}/", timeout=45000,
                                wait_until="domcontentloaded")
                    # O Streamlit pinta por websocket depois do HTML; sem espera
                    # a captura sai em branco e parece página quebrada.
                    pagina.wait_for_timeout(12000)
                    primeira = False
                # Clicar no menu, e não abrir a URL: é o caminho do usuário, e
                # navegação direta com `st.navigation` abre um diálogo de
                # "página não encontrada" antes de resolver a rota.
                link = pagina.query_selector(
                    f'[data-testid="stSidebarNav"] a:has-text("{rotulo}")')
                if link:
                    link.click()
                    pagina.wait_for_timeout(11000)
            except Exception as exc:
                print(f"  {rotulo:<20} não abriu: {type(exc).__name__}")
                problemas += 1
                continue

            corpo = pagina.inner_text("body") or ""
            erro = any(t in corpo for t in ("Traceback", "KeyError",
                                            "AttributeError", "Exception"))
            largura = pagina.evaluate(_LARGURA_JS)
            ocupacao = largura / VIEWPORT["width"] if largura > 0 else 0

            arquivo = destino / f"{rota}.png"
            altura = _capturar(pagina, arquivo)

            alertas = []
            if erro:
                alertas.append("ERRO NA PÁGINA")
            if ocupacao and ocupacao < OCUPACAO_MINIMA:
                alertas.append(f"desperdiça {(1 - ocupacao) * 100:.0f}% da tela")
            problemas += bool(alertas)

            print(f"  {rotulo:<20} {largura:>5}px ({ocupacao * 100:>3.0f}%)  "
                  f"altura {altura:>5}px  {arquivo.name:<18} "
                  f"{' · '.join(alertas)}")

            if rota != "configuracoes":
                continue
            # A primeira seção já saiu na captura acima; as outras cinco só
            # existem depois do clique no segmented_control.
            for indice, secao in enumerate(SECOES_CONFIG):
                if indice == 0:
                    continue
                botao = pagina.query_selector(
                    f'[data-testid="stButtonGroup"] '
                    f'button:has-text("{secao}")')
                if not botao:
                    print(f"    · {secao:<16} seção não encontrada")
                    problemas += 1
                    continue
                botao.click()
                pagina.wait_for_timeout(9000)
                nome = _ascii(secao)
                sub = destino / f"configuracoes_{indice}_{nome}.png"
                altura = _capturar(pagina, sub)
                print(f"    · {secao:<16} altura {altura:>5}px  {sub.name}")

        navegador.close()

    print(f"\n  imagens em {destino}")
    print("  Abra cada uma e avalie como especialista de UI/UX — largura ocupada,")
    print("  densidade, hierarquia. Número não substitui olhar.\n")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "8501"))
