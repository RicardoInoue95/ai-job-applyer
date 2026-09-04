"""API local da extensão: onde mora a decisão, e o que não pode vazar.

A extensão existe para uma coisa que hoje é impossível: o formulário da Gupy fica
atrás de um login protegido por Turnstile, e são 230 vagas da fila. Rodando na
sessão que o candidato já autenticou, não há login a automatizar nem detecção a
evadir — é ele navegando, com ajuda.

A divisão que estes testes protegem: **a extensão é I/O, a decisão é do Python**.
Duplicar a política de resposta em JavaScript criaria a segunda cópia que este
projeto passou o dia consertando.
"""
import pytest
from starlette.testclient import TestClient

from jobapplier import api


@pytest.fixture
def cliente():
    return TestClient(api.criar_app())


# ── Segurança ─────────────────────────────────────────────────────────────────

def test_escuta_so_em_loopback():
    """As respostas carregam CPF e telefone. Em 0.0.0.0 isso vira serviço
    publicado na rede local."""
    assert api.HOST == "127.0.0.1"
    import inspect
    assert 'host: str = HOST' in inspect.getsource(api.servir)


def test_cors_nao_e_curinga():
    """`*` deixaria qualquer página aberta no navegador ler o CPF do candidato."""
    import inspect

    fonte = inspect.getsource(api.criar_app)
    assert 'allow_origins=["*"]' not in fonte
    assert "allow_origin_regex" in fonte
    for dominio in ("gupy", "greenhouse", "lever", "inhire", "linkedin"):
        assert dominio in fonte


def test_saude_responde(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ── Vaga desconhecida ─────────────────────────────────────────────────────────

@pytest.mark.db
def test_url_fora_do_acervo_e_404(cliente):
    r = cliente.get("/vaga", params={"url": "https://naoexiste.gupy.io/job/xyz"})
    assert r.status_code == 404
    assert r.json()["conhecida"] is False


@pytest.mark.db
def test_responder_exige_vaga_conhecida(cliente):
    r = cliente.post("/responder", json={"url": "https://naoexiste.gupy.io/job/x",
                                         "campos": []})
    assert r.status_code == 404


# ── Achar a vaga pela URL do formulário ───────────────────────────────────────

PUBLICO = ("https://pagseguro.gupy.io/job/"
           "eyJqb2JJZCI6MTE1MTA4NDgsInNvdXJjZSI6Imd1cHlfcG9ydGFsIn0="
           "?jobBoardSource=gupy_portal")


@pytest.mark.parametrize("url", [
    PUBLICO,
    "https://pagseguro.gupy.io/jobs/11510848/application",
    "https://pagseguro.gupy.io/jobs/11510848/candidate/dados-adicionais",
])
def test_jobid_sobrevive_a_forma_da_url(url):
    """O acervo guarda a página pública, `/job/<base64>`; a extensão roda no
    formulário, que tem outra URL. Casar por prefixo dava 404 em toda vaga que o
    candidato de fato abriu — e o aviso da extensão culpava o backend."""
    assert api._ids_gupy(url) == {11510848}


def test_id_de_outra_vaga_nao_casa():
    """Frouxidão aqui preencheria o formulário de uma vaga com a resposta de
    outra."""
    assert api._ids_gupy("https://pagseguro.gupy.io/jobs/99999999/application")         != api._ids_gupy(PUBLICO)


@pytest.mark.parametrize("url", [
    "https://pagseguro.gupy.io/candidates/applications/749637585/steps/4205651511/curriculum",
    "https://pagseguro.gupy.io/candidates/applications/11510848/steps/9/x",
])
def test_id_de_candidatura_nunca_e_lido_como_id_de_vaga(url):
    """A URL do formulário traz `applications/<id>/steps/<id>` e nenhum deles é
    o `jobId`. Ler qualquer número do caminho fazia dos dois um candidato — e um
    acerto por coincidência preencheria ESTE formulário com a resposta de OUTRA
    vaga. O segundo caso usa de propósito um `jobId` que existe no acervo."""
    assert api._ids_gupy(url) == set()


def test_segmento_comum_de_caminho_nao_vira_id():
    """`base64.b64decode` aceita quase tudo. Sem exigir JSON com `jobId`,
    qualquer pedaço de caminho viraria um id e casaria vaga errada."""
    for lixo in ("https://x.gupy.io/candidate/additional-information",
                 "https://x.gupy.io/jobs/application/step/review"):
        assert api._ids_gupy(lixo) == set(), lixo


# ── A decisão é a mesma do applicator ─────────────────────────────────────────

def test_responder_usa_auto_answer_e_nao_regra_propria():
    """Se a API reimplementasse a política, a extensão e o applicator
    divergiriam — e a extensão é a que preenche formulário de verdade."""
    import inspect

    fonte = inspect.getsource(api.responder)
    assert "_auto_answer" in fonte
    for reinventado in ("if 'cpf'", 'if "cpf"', "raça", "sensivel"):
        assert reinventado not in fonte, (
            f"a API não pode ter regra própria ({reinventado})")


def test_campo_sem_resposta_vira_manual_e_nunca_chute():
    """Invariante 3, do lado da extensão: `valor: null` e entra em `manuais`."""
    import inspect

    fonte = inspect.getsource(api.responder)
    assert '"valor": valor' in fonte
    assert "manuais.append" in fonte


def test_envio_pela_extensao_e_registrado():
    """Sem isto o envio seria invisível: `ja_candidatado()` não bloquearia um
    reenvio e o funil contaria a menos — o mesmo bug que `finalizar.py` teve."""
    import inspect

    fonte = inspect.getsource(api.marcar_enviada)
    assert "CandidaturaRepository" in fonte


def test_envio_pela_extensao_nao_vira_enviada_confirmada():
    """Quem afirma é o candidato; o sistema não viu a página de confirmação.
    Falso "enviada" bloqueia a vaga para sempre.

    Checa o **import** e o argumento, não a ausência da palavra no arquivo: o
    comentário ali cita `ENVIADA_CONFIRMADA` justamente para explicar por que
    não é usada, e um teste que procura a string puniria a explicação. Foi o
    quinto teste desta base a cair nessa armadilha.
    """
    import inspect

    fonte = inspect.getsource(api.marcar_enviada)
    assert "import REVISAO_MANUAL" in fonte
    assert "import ENVIADA_CONFIRMADA" not in fonte
    assert "status=REVISAO_MANUAL" in fonte


# ── Identificar a candidatura aberta no navegador ─────────────────────────────

def test_id_da_candidatura_sai_da_url_do_formulario():
    """`/candidates/applications/749637585/steps/…` — é o único identificador
    estável que a Gupy oferece nessa tela. Medido na página real: sem
    `__NEXT_DATA__`, sem link para a vaga, sem nada no DOM."""
    assert api.referencia_externa(
        "https://pagseguro.gupy.io/candidates/applications/749637585"
        "/steps/4205651511/curriculum") == ("gupy", "749637585")


@pytest.mark.parametrize("url", [
    "https://pagseguro.gupy.io/job/eyJqb2JJZCI6MTE1MTA4NDh9",
    "https://boards.greenhouse.io/acme/jobs/123456",
    "",
])
def test_url_sem_candidatura_nao_inventa_referencia(url):
    """Vínculo sem id de candidatura ligaria uma vaga a nada, e o próximo
    formulário herdaria o vínculo errado."""
    assert api.referencia_externa(url) is None


def test_id_do_passo_nao_e_confundido_com_o_da_candidatura():
    """A URL tem dois números; só o que vem depois de `applications` é a
    candidatura. Pegar o outro vincularia a vaga ao passo do formulário."""
    plataforma, ref = api.referencia_externa(
        "https://x.gupy.io/candidates/applications/111/steps/222/curriculum")
    assert (plataforma, ref) == ("gupy", "111")
