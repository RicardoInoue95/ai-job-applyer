"""A extensão inteira, contra a API e o banco de verdade — sem login.

`test_extensao_campos.py` testa `campos.js` isolado, injetado numa página. Isto
aqui carrega `extensao/` num Chromium real e percorre o caminho que os testes
unitários não veem: content script → service worker → API em 127.0.0.1:8787 →
banco de respostas → preenchimento. É onde já se esconderam um CSP que matava o
`fetch` do content script e um vínculo de vaga gravado para a aba errada.

Só a página da Gupy é servida localmente: a URL real do formulário
(`/candidates/applications/<id>/steps/<id>`, sem `jobId`) é interceptada e
respondida com uma fixture. Login não entra — o Turnstile da Gupy não serve o
desafio a navegador automatizado, e contorná-lo não é coisa que este projeto
faça.

As perguntas da fixture são inventadas ("teste e2e") de propósito: o teste grava
respostas para elas no banco real e apaga depois, e precisa da certeza de que
não está sobrescrevendo uma resposta do candidato.
"""
import base64
import json
import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.db]

RAIZ = Path(__file__).resolve().parents[2]
EXTENSAO = RAIZ / "extensao"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gupy_teste_e2e.html"

EMPRESA = "Acme Teste E2E"
HOST = "acmeteste-e2e.gupy.io"
JOB_ID = 999000222
TOKEN = base64.b64encode(
    json.dumps({"jobId": JOB_ID, "source": "gupy_portal"}).encode()).decode()
URL_PUBLICA = f"https://{HOST}/job/{TOKEN}?jobBoardSource=gupy_portal"
URL_FORMULARIO = f"https://{HOST}/candidates/applications/999000222/steps/2"

PAGINA_PUBLICA = (
    "<html><head><title>Vaga de teste e2e</title></head><body>"
    "<h1>Vaga de teste e2e</h1>"
    "<a href='/candidates/applications/999000222/steps/2'>Candidatar-se</a>"
    "</body></html>"
)

PERGUNTA_RADIO = "Você aceita participar do teste e2e da extensão?"
PERGUNTA_TEXTO = "Qual a cor de teste e2e da extensão?"


# ── API em 127.0.0.1:8787 ────────────────────────────────────────────────────
# O service worker tem o endereço fixo (`extensao/fundo.js`), então a porta não
# é negociável. Se `run.py` já estiver de pé, usa a API dele; senão sobe uma
# própria numa thread e derruba no fim.

def _porta_ocupada() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", 8787)) == 0


@pytest.fixture(scope="module")
def api():
    if _porta_ocupada():
        yield "externa"
        return
    uvicorn = pytest.importorskip("uvicorn")
    from jobapplier.api import criar_app

    servidor = uvicorn.Server(uvicorn.Config(
        criar_app(), host="127.0.0.1", port=8787, log_level="warning"))
    fio = threading.Thread(target=servidor.run, daemon=True)
    fio.start()
    for _ in range(50):
        if _porta_ocupada():
            break
        time.sleep(0.1)
    else:
        pytest.fail("API não subiu em 127.0.0.1:8787")
    yield "propria"
    servidor.should_exit = True
    fio.join(timeout=5)


# ── Vaga e respostas de teste no banco real ──────────────────────────────────

@pytest.fixture
def acervo():
    from jobapplier import aprendizado
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import RespostaAprendida, Vaga, VinculoCandidatura

    def _limpar():
        with get_session() as s:
            s.query(VinculoCandidatura).filter_by(
                referencia=str(JOB_ID)).delete(synchronize_session=False)
            s.query(Vaga).filter_by(empresa=EMPRESA).delete(synchronize_session=False)
            s.query(RespostaAprendida).filter(
                RespostaAprendida.pergunta.ilike("%teste e2e%")
            ).delete(synchronize_session=False)

    _limpar()
    with get_session() as s:
        vaga = Vaga(hash=f"e2e-{JOB_ID}", titulo="Vaga de teste e2e", empresa=EMPRESA,
                    plataforma="gupy", descricao="teste", link=URL_PUBLICA,
                    status="pronta_envio_manual", score=90)
        s.add(vaga)
        s.flush()
        vaga_id = vaga.id
        aprendizado.registrar(s, PERGUNTA_RADIO, "Não", empresa=EMPRESA,
                              opcoes=["Sim", "Não"])
        aprendizado.registrar(s, PERGUNTA_TEXTO, "Azul e2e", empresa=EMPRESA)
    yield vaga_id
    _limpar()


# ── Chromium com a extensão ──────────────────────────────────────────────────

@pytest.fixture
def navegador(playwright_sync, tmp_path):
    try:
        # `channel="chromium"` é o headless novo, o único que carrega extensão
        # sem janela. Contexto persistente porque extensão exige perfil.
        contexto = playwright_sync.chromium.launch_persistent_context(
            str(tmp_path / "perfil"), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXTENSAO}",
                  f"--load-extension={EXTENSAO}"],
        )
    except Exception as exc:
        pytest.skip(f"Chromium com extensão indisponível ({exc})")
    if not contexto.service_workers:
        contexto.wait_for_event("serviceworker", timeout=15000)
    yield contexto
    contexto.close()


def _rotear(route, request):
    url = request.url
    if url.startswith(URL_PUBLICA.split("?")[0]):
        route.fulfill(status=200, content_type="text/html; charset=utf-8",
                      body=PAGINA_PUBLICA)
    elif url.startswith(URL_FORMULARIO):
        route.fulfill(status=200, content_type="text/html; charset=utf-8",
                      body=FIXTURE.read_text(encoding="utf-8"))
    else:
        route.abort()


def test_extensao_preenche_o_formulario_da_gupy(api, acervo, navegador):
    page = navegador.pages[0] if navegador.pages else navegador.new_page()
    page.route(f"https://{HOST}/**", _rotear)

    # 1. Página pública: é a única com o jobId, e o content script avisa o
    #    service worker de qual vaga está nesta aba.
    page.goto(URL_PUBLICA, wait_until="load")
    page.wait_for_timeout(800)

    # 2. Formulário, na mesma aba, sem jobId na URL. A extensão tem de resolver
    #    a vaga pela memória da aba (ou pelo referrer), perguntar à API e
    #    escrever. O primeiro preenchimento dispara 1,2 s depois do load.
    page.click("text=Candidatar-se")
    page.wait_for_url(URL_FORMULARIO + "*")
    page.wait_for_function("document.querySelector('#e2e_cor').value !== ''",
                           timeout=15000)

    assert page.input_value("#e2e_cor") == "Azul e2e"
    assert page.is_checked("#e2e_nao") and not page.is_checked("#e2e_sim")
    # Pergunta sem resposta no banco fica em branco: nunca um chute (inv. 3).
    assert page.input_value("#e2e_livre") == ""

    # O aviso diz o que fez e o que ficou para você — pelo nome da pergunta,
    # para não ter de caçar o campo vazio no formulário.
    aviso = page.text_content("#aija-aviso") or ""
    assert "2 campos preenchidos" in aviso
    assert "2 do banco de respostas" in aviso
    assert "1 ficaram para você" in aviso
    assert "Pergunta de teste e2e sem resposta no banco?" in aviso

    # Não existe botão de enviar na fixture, e mesmo que existisse a extensão
    # não o clicaria: `tests/unit/test_extensao.py` garante isso no código.


def test_extensao_grava_o_vinculo_da_aba(api, acervo, navegador):
    """Resolvida pela memória da aba, a vaga fica vinculada ao formulário: na
    próxima visita — vindo por e-mail, sem referrer — a API acha direto."""
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import VinculoCandidatura

    page = navegador.pages[0] if navegador.pages else navegador.new_page()
    page.route(f"https://{HOST}/**", _rotear)
    page.goto(URL_PUBLICA, wait_until="load")
    page.wait_for_timeout(800)
    page.click("text=Candidatar-se")
    page.wait_for_function("document.querySelector('#e2e_cor').value !== ''",
                           timeout=15000)

    with get_session() as s:
        vinculo = (s.query(VinculoCandidatura)
                   .filter_by(referencia=str(JOB_ID)).one_or_none())
        assert vinculo is not None
        assert vinculo.vaga_id == acervo
        assert vinculo.origem in ("aba", "referrer")
