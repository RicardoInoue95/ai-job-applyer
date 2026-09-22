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


# ── Perfil do LinkedIn ────────────────────────────────────────────────────────
# A extensão lê o perfil na aba do candidato e manda para cá. A API é quem
# garante que é o perfil DELE: a permissão do content script cobre `/in/*`
# inteiro, e a única barreira contra guardar dado de terceiro é esta.

_MESTRE_LI = {
    "linkedin": "https://www.linkedin.com/in/fulano-teste/",
    "resumo_profissional": "Resumo.",
    "experiencias": [{"empresa": "Acme", "cargo": "Coordenador de Dados",
                      "data_inicio": "08/2025", "data_fim": None}],
    "formacao": [], "tecnologias": ["SQL", "Python"],
}


@pytest.fixture
def perfil_isolado(monkeypatch, tmp_path):
    from jobapplier import perfil_linkedin as mod

    monkeypatch.setattr(api, "_resume", lambda: _MESTRE_LI)
    monkeypatch.setattr(mod, "ARQUIVO", tmp_path / "perfil_linkedin.json")
    # Sem banco: o mercado vem pronto.
    monkeypatch.setattr(mod, "mercado", lambda sessao, limite=15: [("SQL", 10), ("Python", 8)])

    class _Sessao:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("jobapplier.database.connection.get_session", lambda: _Sessao())
    return mod


def test_perfil_de_terceiro_e_403_e_nao_grava(cliente, perfil_isolado):
    r = cliente.post("/perfil_linkedin", json={
        "url": "https://www.linkedin.com/in/outra-pessoa/",
        "perfil": {"titulo": "x"}})
    assert r.status_code == 403
    assert not perfil_isolado.ARQUIVO.exists()


def test_perfil_ausente_e_400(cliente, perfil_isolado):
    r = cliente.post("/perfil_linkedin", json={"url": _MESTRE_LI["linkedin"]})
    assert r.status_code == 400


def test_meu_perfil_e_analisado_e_guardado(cliente, perfil_isolado):
    perfil = {"titulo": "", "sobre": "", "competencias": ["SQL"],
              "experiencias": [{"cargo": "Coordenador de Dados", "empresa": "Acme",
                                "periodo": "ago de 2025 - o momento"}],
              "formacao": []}
    r = cliente.post("/perfil_linkedin", json={
        "url": "https://www.linkedin.com/in/Fulano-Teste?locale=pt", "perfil": perfil})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["cobertura"] == [1, 2]
    areas = {a["area"] for a in corpo["ajustes"]}
    assert {"titulo", "sobre"} <= areas
    assert perfil_isolado.ARQUIVO.exists()
    assert perfil_isolado.carregar()["perfil"]["competencias"] == ["SQL"]


# ── Fila e decisão ────────────────────────────────────────────────────────────
# O painel da extensão e o webapp leem daqui. O contrato importa mais que os
# dados: dois clientes renderizando a mesma coisa só ficam iguais se a forma
# da resposta for uma.

def test_fila_padrao_e_o_que_precisa_de_voce(cliente, monkeypatch):
    """O painel percorre a mesma lista que o contador da barra do webapp conta:
    excelentes com dossiê. O acervo inteiro só sai com `tudo=1`."""
    from jobapplier import fila as mod

    chamadas = {}
    monkeypatch.setattr(mod, "precisam_de_voce",
                        lambda: chamadas.setdefault("precisam", True) and [])
    monkeypatch.setattr(mod, "corte_de_atencao", lambda: 85)
    monkeypatch.setattr(mod, "listar",
                        lambda **k: chamadas.setdefault("listar", k) and [])
    r = cliente.get("/fila")
    assert r.status_code == 200
    assert r.json()["corte"] == 85
    assert "precisam" in chamadas and "listar" not in chamadas


def test_fila_com_tudo_usa_o_acervo(cliente, monkeypatch):
    from jobapplier import fila as mod

    visto = {}

    def _listar(**kwargs):
        visto.update(kwargs)
        return []

    monkeypatch.setattr(mod, "listar", _listar)
    monkeypatch.setattr(mod, "do_dia", lambda q=5: pytest.fail("usou a fila curta"))
    r = cliente.get("/fila", params={"tudo": "1", "score_min": "70"})
    assert r.status_code == 200
    assert visto["score_min"] == 70


def test_decisao_so_aceita_as_conhecidas(cliente, monkeypatch):
    """Aceitar status arbitrário deixaria um POST gravar 'enviada_confirmada'
    sem prova, e `ja_candidatado` bloquearia a vaga para sempre."""
    from jobapplier import fila as mod

    monkeypatch.setattr(mod, "decidir", mod.decidir)  # sem stub: valida de fato
    r = cliente.post("/vaga/1/decisao", json={"decisao": "enviada_confirmada"})
    assert r.status_code == 400
    assert r.json()["erro"]["codigo"]


def test_decisao_conhecida_chega_ao_servico(cliente, monkeypatch):
    from jobapplier import fila as mod

    visto = {}

    def _decidir(vaga_id, decisao):
        visto.update(vaga_id=vaga_id, decisao=decisao)
        return {"ok": True, "vaga_id": vaga_id, "de": "aprovada", "para": "adiada"}

    monkeypatch.setattr(mod, "decidir", _decidir)
    r = cliente.post("/vaga/42/decisao", json={"decisao": "adiar"})
    assert r.status_code == 200
    assert visto == {"vaga_id": 42, "decisao": "adiar"}


def test_dossie_de_vaga_inexistente_usa_o_catalogo(cliente, monkeypatch):
    from jobapplier import fila as mod

    monkeypatch.setattr(mod, "dossie", lambda vaga_id: {})
    r = cliente.get("/vaga/999999/dossie")
    assert r.status_code == 404
    assert r.json()["erro"]["codigo"] == "vaga-inexistente"
    assert r.json()["erro"]["acao"]


def test_situacao_do_perfil_diz_o_slug_e_quando_foi_lido(cliente, perfil_isolado):
    """É o que a extensão consulta para decidir se lê sozinha: só o SEU slug,
    e só se a última leitura estiver velha."""
    r = cliente.get("/perfil_linkedin")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["slug"] == "fulano-teste"
    assert corpo["lido_em"] is None
    assert corpo["dias_para_reler"] >= 1


@pytest.mark.parametrize("url, esperado", [
    ("https://www.linkedin.com/jobs/view/4455387424/", "4455387424"),
    ("https://www.linkedin.com/jobs/view/4455387424/?refId=abc", "4455387424"),
    ("https://www.linkedin.com/jobs/search/?currentJobId=4455387424&keywords=dados", "4455387424"),
    ("https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4455387424", "4455387424"),
    # sem id não se deduz por título nem por nada
    ("https://www.linkedin.com/jobs/search/?keywords=dados", None),
    ("https://www.linkedin.com/in/ricardo/", None),
    # id da Gupy não é id do LinkedIn
    ("https://acme.gupy.io/jobs/4455387424", None),
])
def test_id_do_linkedin_vem_da_url_da_vaga_ou_do_currentjobid(url, esperado):
    """O acervo guarda `/jobs/view/<id>/`; o candidato chega pelo Easy Apply
    aberto da busca, onde o id só está em `currentJobId`."""
    from jobapplier import api

    assert api._id_linkedin(url) == esperado
