"""O coletor da Gupy devolvia zero vagas em silêncio, por dois motivos somados.

O endpoint tinha migrado (404, visível no log) e, mesmo com o endpoint certo,
todo item era descartado por exigir `careerPageSlug` — campo que a resposta
atual não traz. O segundo é o modo de falha perigoso: 404 aparece no log, campo
ausente não. O log dizia "0 vagas" como se a busca não tivesse resultado, e
ficou assim tempo suficiente para o banco acumular 11.228 vagas do Greenhouse
e nenhuma da Gupy.

Estes testes não tocam rede: o payload abaixo é a forma real da resposta,
capturada de `employability-portal.gupy.io/api/v1/jobs`.
"""
import pytest

from jobapplier.collectors import gupy

ITEM = {
    "id": 12147158,
    "companyId": 203,
    "name": "Engenheiro de Dados Pleno | Plataforma de Dados",
    "description": "<p>Com uma trajetória de <b>95 anos</b>&nbsp;...</p>",
    "careerPageId": 118513,
    "careerPageName": "Americanas S.A.",
    "careerPageUrl": "https://americanas.gupy.io/eyJzb3VyY2UiOiJndXB5X3BvcnRhbCJ9",
    "publishedDate": "2026-08-17T18:18:05.626Z",
    "isRemoteWork": False,
    "city": "Rio de Janeiro",
    "state": "Rio de Janeiro",
    "country": "Brasil",
    "jobUrl": "https://americanas.gupy.io/job/eyJqb2JJZCI6MTIxNDcxNTh9",
    "workplaceType": "hybrid",
}


# ── Conversão de item ─────────────────────────────────────────────────────────

def test_item_real_da_api_vira_vaga():
    """A regressão em uma linha: este item era descartado por não ter
    `careerPageSlug`."""
    v = gupy._para_vaga(ITEM)
    assert v is not None
    assert v.titulo == "Engenheiro de Dados Pleno | Plataforma de Dados"
    assert v.empresa == "Americanas S.A."
    assert v.plataforma == "gupy"
    assert v.fonte_vaga_id == "12147158"
    assert v.hash, "hash é o que deduplica no banco"


def test_usa_o_joburl_da_api_e_nao_monta_a_mao():
    """O link da API já carrega o token de origem e é o que a Gupy espera de
    volta. Montar `https://{slug}.gupy.io/jobs/{id}` produzia URL que não
    corresponde ao que o portal serve."""
    assert gupy._para_vaga(ITEM).link == ITEM["jobUrl"]


def test_sem_joburl_cai_para_o_slug_quando_ele_existe():
    item = {**ITEM, "jobUrl": ""}
    v = gupy._para_vaga(item, slug_padrao="americanas")
    assert v.link == "https://americanas.gupy.io/jobs/12147158"


def test_sem_joburl_e_sem_slug_descarta():
    """Vaga sem link é inútil: não dá para candidatar nem revisar."""
    assert gupy._para_vaga({**ITEM, "jobUrl": ""}) is None


@pytest.mark.parametrize("faltando", ["id", "name"])
def test_campo_essencial_ausente_descarta(faltando):
    assert gupy._para_vaga({**ITEM, faltando: ""}) is None


def test_identidade_da_empresa_usa_careerpageid():
    """Sem slug na resposta, a identidade estável é o id do career page."""
    assert gupy._para_vaga(ITEM).fonte_empresa_id == "118513"


# ── Modalidade ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo,esperado", [
    ("remote", "remoto"),
    ("hybrid", "híbrido"),
    ("on-site", "presencial"),
    ("on_site", "presencial"),
])
def test_workplacetype_mapeia_para_o_vocabulario(tipo, esperado):
    assert gupy._modalidade({"workplaceType": tipo}) == esperado


def test_hibrido_nao_vira_presencial():
    """`isRemoteWork` é booleano e colapsa híbrido em presencial. Numa coleta
    real são 88 de 209 vagas — e híbrido em São Paulo é exatamente o caso que
    interessa, então o filtro 4B as descartava como presencial em outro estado."""
    item = {"workplaceType": "hybrid", "isRemoteWork": False}
    assert gupy._modalidade(item) == "híbrido"


def test_booleano_e_so_reserva():
    assert gupy._modalidade({"isRemoteWork": True}) == "remoto"
    assert gupy._modalidade({"isRemoteWork": False}) == "presencial"
    assert gupy._modalidade({}) is None


def test_workplacetype_desconhecido_cai_para_o_booleano():
    assert gupy._modalidade({"workplaceType": "novo_modo", "isRemoteWork": True}) == "remoto"


# ── Descrição ─────────────────────────────────────────────────────────────────

def test_html_e_removido_da_descricao():
    """O filtro 4A casa por palavra; tag no meio do texto atrapalha o match."""
    limpo = gupy._limpar("<p>Buscamos <b>Python</b>&nbsp;e SQL</p>")
    assert "<" not in limpo and ">" not in limpo
    assert "Python" in limpo and "SQL" in limpo
    assert "&nbsp;" not in limpo


def test_entidades_html_viram_caracteres():
    assert gupy._limpar("R&amp;D &lt;dados&gt;") == "R&D <dados>"


def test_descricao_vazia_nao_quebra():
    assert gupy._limpar("") == ""
    assert gupy._para_vaga({**ITEM, "description": None}).descricao == ""


# ── Localização e data ────────────────────────────────────────────────────────

def test_localizacao_concatena_o_que_existe():
    assert gupy._localizacao(ITEM) == "Rio de Janeiro, Rio de Janeiro, Brasil"
    assert gupy._localizacao({"city": "", "state": "", "country": ""}) is None
    assert gupy._localizacao({"city": "Recife"}) == "Recife"


def test_data_de_publicacao_iso_com_z():
    d = gupy._para_vaga(ITEM).data_publicacao
    assert d is not None and d.year == 2026 and d.month == 8


def test_data_invalida_nao_derruba_a_vaga():
    """Uma data mal formada não pode custar a vaga inteira."""
    v = gupy._para_vaga({**ITEM, "publishedDate": "não é data"})
    assert v is not None and v.data_publicacao is None


# ── Busca ─────────────────────────────────────────────────────────────────────

class _Resposta:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_busca_deduplica_a_mesma_vaga_em_keywords_diferentes(monkeypatch):
    """A mesma vaga responde a 'analista de dados' e a 'power bi'."""
    payload = {"data": [ITEM], "pagination": {"total": 1}}
    monkeypatch.setattr(gupy.requests, "get", lambda *a, **k: _Resposta(payload))

    vagas = gupy.GupyCollector().collect_by_search(["analista de dados", "power bi"])
    assert len(vagas) == 1


def test_busca_avisa_quando_descarta_tudo(monkeypatch, caplog):
    """O modo de falha anterior, exatamente: 100% descartado e lista vazia
    devolvida como se a busca não tivesse resultado. Um coletor que descarta
    tudo precisa gritar."""
    ruim = {"id": 1, "name": "", "jobUrl": ""}
    monkeypatch.setattr(
        gupy.requests, "get",
        lambda *a, **k: _Resposta({"data": [ruim], "pagination": {"total": 1}}),
    )

    with caplog.at_level("WARNING"):
        vagas = gupy.GupyCollector().collect_by_search(["dados"])

    assert vagas == []
    assert any("descartados" in r.message for r in caplog.records), \
        "descarte em massa tem que aparecer no log"


def test_resposta_que_nao_e_json_e_distinguivel_de_busca_sem_resultado(monkeypatch, caplog):
    """200 com corpo HTML é o sintoma de o endpoint ter mudado de novo — não pode
    parecer 'keyword sem vagas'."""
    class _HTML(_Resposta):
        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr(gupy.requests, "get", lambda *a, **k: _HTML(None))
    with caplog.at_level("ERROR"):
        assert gupy.GupyCollector().collect_by_search(["dados"]) == []
    assert any("não é JSON" in r.message for r in caplog.records)


def test_erro_de_rede_numa_keyword_nao_derruba_as_outras(monkeypatch):
    chamadas = {"n": 0}

    def get(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise gupy.requests.RequestException("timeout")
        return _Resposta({"data": [ITEM], "pagination": {"total": 1}})

    monkeypatch.setattr(gupy.requests, "get", get)
    vagas = gupy.GupyCollector().collect_by_search(["primeira", "segunda"])
    assert len(vagas) == 1, "a segunda keyword tem que ser tentada"


def test_endpoint_e_parametro_atuais():
    """Trava a migração: o endpoint e o nome do parâmetro mudaram juntos, e o
    antigo responde 404."""
    assert gupy.PORTAL_API == "https://employability-portal.gupy.io/api/v1/jobs"
    assert "portal.api.gupy.io" not in gupy.PORTAL_API


@pytest.mark.live
def test_api_da_gupy_continua_respondendo():
    """Só sob demanda (`pytest -m live`): confirma que o contrato não mudou.

    Boards públicos, sem login, sem submeter nada — dentro do que a invariante 6
    permite para teste com rede."""
    import requests

    r = requests.get(gupy.PORTAL_API, params={"jobName": "engenheiro de dados",
                                              "limit": 5, "offset": 0},
                     headers=gupy.HEADERS, timeout=20)
    assert r.status_code == 200
    dados = r.json()
    assert dados.get("data"), "a API parou de devolver vagas"
    primeiro = dados["data"][0]
    for campo in ("id", "name", "jobUrl", "careerPageName", "workplaceType"):
        assert campo in primeiro, f"campo '{campo}' sumiu da resposta"
