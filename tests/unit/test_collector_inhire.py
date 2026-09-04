"""Coletor da inhire: uma requisição por empresa, sem autenticação.

`api.inhire.app/job-posts/public/pages` com header `x-tenant` devolve a lista
inteira — 126 vagas de uma empresa numa resposta só, sem paginação. O `x-tenant`
não é credencial: é o identificador público do career page, o mesmo que aparece
em `https://<slug>.inhire.app/vagas`.

A lista é magra de propósito, então a descrição exige uma chamada por vaga. Sem
descrição a vaga não passa no filtro 4A — mas abrir 126 páginas para descobrir
que 120 são de outra área é desperdício de rede. Daí `detalhar` ser separado de
`collect`, e chamado só depois de filtrar por título.
"""
import pytest

from jobapplier.collectors import inhire
from jobapplier.collectors.inhire import InhireCollector

PAGINA = {
    "tenantName": "Radix",
    "jobsPage": [
        {"jobId": "5f1a8985-0b08", "displayName": " Profissional Business Analyst ",
         "status": "published", "workplaceType": "Remote", "location": "BR"},
        {"jobId": "87de7c72-063a", "displayName": "Analista de Dados Pleno",
         "status": "published", "workplaceType": "Hybrid",
         "city": "Rio de Janeiro", "state": "RJ", "location": "BR"},
        {"jobId": "aaa", "displayName": "Vaga fechada",
         "status": "closed", "workplaceType": "Remote", "location": "BR"},
    ],
}


class _Resposta:
    def __init__(self, payload=None, status=200, texto=""):
        self._payload = payload
        self.status_code = status
        self.text = texto

    def raise_for_status(self):
        if self.status_code >= 400:
            raise inhire.requests.RequestException(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise ValueError("não é JSON")
        return self._payload


@pytest.fixture
def responder(monkeypatch):
    def instalar(resposta):
        monkeypatch.setattr(inhire.requests, "get", lambda *a, **k: resposta)
    return instalar


# ── Coleta ────────────────────────────────────────────────────────────────────

def test_coleta_so_as_publicadas(responder):
    """`status: closed` é vaga que saiu do ar. Coletá-la enche a fila com o que
    não dá para candidatar."""
    responder(_Resposta(PAGINA))
    vagas = InhireCollector().collect("radix")

    assert len(vagas) == 2
    assert all("fechada" not in v.titulo.lower() for v in vagas)


def test_campos_essenciais(responder):
    responder(_Resposta(PAGINA))
    v = InhireCollector().collect("radix")[0]

    assert v.titulo == "Profissional Business Analyst", "espaços nas pontas somem"
    assert v.empresa == "Radix"
    assert v.plataforma == "inhire"
    assert v.fonte_vaga_id == "5f1a8985-0b08"
    assert v.fonte_empresa_id == "radix"
    assert v.hash, "sem hash não há dedup"


def test_link_aponta_para_o_career_page(responder):
    responder(_Resposta(PAGINA))
    assert InhireCollector().collect("radix")[0].link == \
        "https://radix.inhire.app/vagas/5f1a8985-0b08"


@pytest.mark.parametrize("tipo,esperado", [
    ("Remote", "remoto"), ("Hybrid", "híbrido"),
    ("On-site", "presencial"), ("Office", "presencial"),
])
def test_modalidade_traduzida(tipo, esperado, responder):
    responder(_Resposta({"tenantName": "X", "jobsPage": [
        {"jobId": "1", "displayName": "T", "status": "published",
         "workplaceType": tipo, "location": "BR"}]}))
    assert InhireCollector().collect("x")[0].modalidade == esperado


def test_pais_vira_nome_e_nao_sigla(responder):
    """`location` vem como "BR". Sem traduzir, a checagem geográfica lê a sigla
    como lugar desconhecido e descarta a vaga como estrangeira."""
    responder(_Resposta(PAGINA))
    vagas = InhireCollector().collect("radix")

    assert vagas[0].localizacao == "Brasil"
    assert vagas[1].localizacao == "Rio de Janeiro, RJ, Brasil"


def test_vaga_sem_id_ou_titulo_e_descartada(responder):
    responder(_Resposta({"tenantName": "X", "jobsPage": [
        {"jobId": "", "displayName": "Sem id", "status": "published"},
        {"jobId": "1", "displayName": "", "status": "published"},
    ]}))
    assert InhireCollector().collect("x") == []


def test_empresa_sem_vagas_nao_e_erro(responder):
    responder(_Resposta({"tenantName": "X", "jobsPage": []}))
    assert InhireCollector().collect("x") == []


def test_erro_de_rede_devolve_vazio(monkeypatch):
    def explode(*a, **k):
        raise inhire.requests.RequestException("timeout")

    monkeypatch.setattr(inhire.requests, "get", explode)
    assert InhireCollector().collect("x") == []


def test_resposta_que_nao_e_json_e_logada_como_erro(responder, caplog):
    """200 com corpo HTML significa endpoint mudado — não pode parecer 'empresa
    sem vagas'."""
    responder(_Resposta(None, texto="<html>"))
    with caplog.at_level("ERROR"):
        assert InhireCollector().collect("x") == []
    assert any("não é JSON" in r.message for r in caplog.records)


# ── Detalhe ───────────────────────────────────────────────────────────────────

def test_detalhar_preenche_a_descricao(responder):
    responder(_Resposta(PAGINA))
    vagas = InhireCollector().collect("radix")
    assert all(not v.descricao for v in vagas), "a lista não traz descrição"

    responder(_Resposta({"description": "<p>Buscamos <b>Python</b> e SQL</p>"}))
    assert InhireCollector().detalhar(vagas, "radix") == 2
    assert "Python" in vagas[0].descricao
    assert "<" not in vagas[0].descricao


def test_detalhar_respeita_o_teto(responder):
    """Cada detalhe é uma requisição. Empresa grande tem cem vagas das quais
    poucas interessam."""
    responder(_Resposta({"tenantName": "X", "jobsPage": [
        {"jobId": str(i), "displayName": f"Vaga {i}", "status": "published",
         "location": "BR"} for i in range(10)]}))
    vagas = InhireCollector().collect("x")

    chamadas = {"n": 0}

    def contar(*a, **k):
        chamadas["n"] += 1
        return _Resposta({"description": "texto"})

    import jobapplier.collectors.inhire as mod
    mod.requests.get = contar
    InhireCollector().detalhar(vagas, "x", limite=3)
    assert chamadas["n"] == 3


def test_detalhar_nao_refaz_quem_ja_tem_descricao(responder):
    responder(_Resposta(PAGINA))
    vagas = InhireCollector().collect("radix")
    vagas[0].descricao = "já tenho"

    responder(_Resposta({"description": "nova"}))
    InhireCollector().detalhar(vagas, "radix")
    assert vagas[0].descricao == "já tenho"


# ── Limpeza de HTML ───────────────────────────────────────────────────────────

def test_entidades_em_portugues_viram_acento():
    """A inhire devolve entidades nomeadas: sem traduzir, "gest&atilde;o" não
    casa com "gestão" no filtro 4A e o vocabulário perde o termo."""
    limpo = inhire._limpar("<p>Experi&ecirc;ncia em gest&atilde;o de servi&ccedil;os</p>")
    assert limpo == "Experiência em gestão de serviços"


def test_limpeza_de_vazio():
    assert inhire._limpar("") == ""
    assert inhire._limpar(None) == ""


# ── Contrato ──────────────────────────────────────────────────────────────────

def test_registrada_no_registro_de_plataformas():
    from jobapplier import plataformas

    p = plataformas.obter("inhire")
    assert p is not None and p.coletor == "inhire"


@pytest.mark.live
def test_api_real_continua_respondendo():
    """Só sob demanda (`pytest -m live`). Endpoint público, sem login, sem enviar
    nada — dentro do que a invariante 6 permite."""
    vagas = InhireCollector().collect("radix")
    assert vagas, "a API parou de devolver vagas"
    assert all(v.link and v.fonte_vaga_id for v in vagas)
