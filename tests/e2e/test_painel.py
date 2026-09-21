"""O painel lateral, carregado como página da extensão, contra a API real.

O que se prova: a inbox abre com o mesmo conjunto que a API chama de "precisam
de você", o contador acompanha a navegação por teclado, e a evidência (nível 2)
só é buscada quando aberta. Não decide nada: "enviei" e "não é para mim"
escrevem no banco real, e um teste que grava decisão sobre vaga sua é um teste
que apaga trabalho seu.

Reusa a API do `run.py` se estiver de pé; senão sobe uma. O build do painel
(`extensao/painel/`) precisa existir — `npm run build` em `painel/` — e o teste
pula se não existir, porque build não é coisa de suíte de teste.
"""
from pathlib import Path

import pytest

from tests.e2e.test_extensao_ponta_a_ponta import EXTENSAO, api  # noqa: F401

pytestmark = [pytest.mark.e2e, pytest.mark.db]

PAINEL = EXTENSAO / "painel" / "index.html"


@pytest.fixture
def painel(playwright_sync, tmp_path):
    if not PAINEL.exists():
        pytest.skip("painel não construído: cd painel && npm run build")
    try:
        contexto = playwright_sync.chromium.launch_persistent_context(
            str(tmp_path / "perfil"), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXTENSAO}",
                  f"--load-extension={EXTENSAO}"],
            viewport={"width": 400, "height": 900},
        )
    except Exception as exc:
        pytest.skip(f"Chromium com extensão indisponível ({exc})")
    if not contexto.service_workers:
        contexto.wait_for_event("serviceworker", timeout=15000)
    ext_id = contexto.service_workers[0].url.split("/")[2]
    page = contexto.pages[0] if contexto.pages else contexto.new_page()
    page.goto(f"chrome-extension://{ext_id}/painel/index.html", wait_until="load")
    yield page
    contexto.close()


def _fila_da_api() -> list[dict]:
    import requests

    return requests.get("http://127.0.0.1:8787/fila", timeout=10).json()["vagas"]


def test_inbox_mostra_o_que_precisa_de_voce(api, painel):  # noqa: F811
    esperadas = _fila_da_api()
    if not esperadas:
        pytest.skip("fila vazia neste banco")
    painel.wait_for_selector(".contador", timeout=15000)
    assert painel.text_content(".contador").strip() == f"1 / {len(esperadas)}"
    assert painel.text_content(".titulo-vaga").strip() == esperadas[0]["titulo"]
    # Nível 1 no cartão; nível 2 fechado.
    assert painel.query_selector(".ader") is not None
    assert painel.query_selector(".eixo") is None


def test_setas_navegam_sem_recarregar(api, painel):  # noqa: F811
    esperadas = _fila_da_api()
    if len(esperadas) < 2:
        pytest.skip("precisa de duas vagas na fila")
    painel.wait_for_selector(".contador", timeout=15000)
    painel.keyboard.press("ArrowRight")
    painel.wait_for_timeout(300)
    assert painel.text_content(".contador").strip() == f"2 / {len(esperadas)}"
    assert painel.text_content(".titulo-vaga").strip() == esperadas[1]["titulo"]
    painel.keyboard.press("ArrowLeft")
    painel.wait_for_timeout(300)
    assert painel.text_content(".contador").strip() == f"1 / {len(esperadas)}"


def test_evidencia_so_carrega_ao_abrir(api, painel):  # noqa: F811
    if not _fila_da_api():
        pytest.skip("fila vazia neste banco")
    painel.wait_for_selector(".contador", timeout=15000)
    painel.click("text=por que combina")
    painel.wait_for_selector(".eixo", timeout=15000)
    assert len(painel.query_selector_all(".eixo")) >= 1


def test_atalho_nao_dispara_dentro_de_campo_de_texto(api, painel):  # noqa: F811
    """"a" e "e" decidem vagas. Dentro de um input teriam de ser letras."""
    if not _fila_da_api():
        pytest.skip("fila vazia neste banco")
    painel.wait_for_selector(".contador", timeout=15000)
    antes = painel.text_content(".contador")
    painel.evaluate("""() => {
        const i = document.createElement('input'); i.id = 'campo-teste';
        document.body.appendChild(i); i.focus();
    }""")
    painel.keyboard.type("ae")
    painel.wait_for_timeout(300)
    assert painel.input_value("#campo-teste") == "ae"
    assert painel.text_content(".contador") == antes


def test_painel_esta_no_gitignore_e_no_manifest():
    """O build é gerado, não versionado; e o manifest tem de apontar para ele."""
    import json

    raiz = Path(__file__).resolve().parents[2]
    assert "extensao/painel/" in (raiz / ".gitignore").read_text(encoding="utf-8")
    manifest = json.loads((EXTENSAO / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["side_panel"]["default_path"] == "painel/index.html"
    assert "sidePanel" in manifest["permissions"]
