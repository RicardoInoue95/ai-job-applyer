"""O campo `localizacao` é sinal geográfico melhor que a descrição.

A extração textual conhecia quatro países — US, CA, GB, BR —, lista escrita
quando o pipeline só tinha Greenhouse, que é ATS americano. Com a Gupy entraram
vagas do Chile, do México e de Portugal, nenhum deles reconhecido.

O caso que expôs isso: "Data Engineer [remote from EU]", `localizacao` igual a
"Portugal", **score 86** — perto do topo da lista, para uma vaga que exige
autorização de trabalho na União Europeia. Nem "Portugal" nem "remote from EU"
casavam com nada.
"""
from types import SimpleNamespace

import pytest

from jobapplier.agents.extracao import normalizar
from jobapplier.elegibilidade import (
    Elegibilidade,
    avaliar_normalizado,
    pais_de_localizacao,
)

# ── Classificação do campo estruturado ────────────────────────────────────────

@pytest.mark.parametrize("local", [
    "Brasil",
    "São Paulo, São Paulo, Brasil",
    "Rio de Janeiro, Rio de Janeiro",
    "Salvador, Bahia",
    "Goiânia, Goiás",
    "Campinas, SP",
    "Brazil",
])
def test_locais_brasileiros(local):
    assert pais_de_localizacao(local) == "BR"


def test_estado_sem_pais_ainda_e_brasil():
    """8 das 320 vagas coletadas vinham só como 'São Paulo, São Paulo'. Lê-las
    como estrangeiras descartaria vaga boa em silêncio — o erro mais caro deste
    filtro, porque não deixa rastro."""
    assert pais_de_localizacao("São Paulo, São Paulo") == "BR"
    assert pais_de_localizacao("Belo Horizonte, Minas Gerais") == "BR"


def test_acento_nao_muda_a_classificacao():
    assert pais_de_localizacao("Goiania, Goias") == "BR"
    assert pais_de_localizacao("GOIÂNIA, GOIÁS") == "BR"


@pytest.mark.parametrize("local", [
    "Portugal",
    "Ciudad de México, México",
    "Santiago, Chile",
    "Lisboa, Portugal",
    "Buenos Aires, Argentina",
])
def test_locais_estrangeiros(local):
    """'XX' é 'fora do Brasil' sem dizer qual país — é tudo o que o filtro
    precisa saber, e evita manter uma lista de países do mundo."""
    assert pais_de_localizacao(local) == "XX"


@pytest.mark.parametrize("local", ["", "   ", "Remoto", "Home office",
                                   "remote", "A combinar", None])
def test_local_generico_nao_afirma_pais(local):
    """Indeterminado não descarta ninguém: 'Remoto' não diz de onde."""
    assert pais_de_localizacao(local) is None


def test_pais_estrangeiro_junto_de_estado_brasileiro_vence_o_brasil():
    """Vaga listada em duas praças: se uma delas é no Brasil, ele pode trabalhar."""
    assert pais_de_localizacao("São Paulo, Brasil / Lisboa, Portugal") == "BR"


# ── Ponta a ponta pelo 4B ─────────────────────────────────────────────────────

def _vaga(titulo, local, descricao="Python, SQL, Snowflake"):
    return SimpleNamespace(id=1, titulo=titulo, empresa="Acme", localizacao=local,
                           descricao=descricao, plataforma="gupy")


def test_a_vaga_de_portugal_e_rejeitada():
    """A regressão exata: score 86, no topo da lista, inutilizável."""
    a = avaliar_normalizado(normalizar(
        _vaga("Data Engineer [remote from EU]", "Portugal")
    ))
    assert a.estado is Elegibilidade.INELEGIVEL


@pytest.mark.parametrize("titulo,local", [
    ("Data Analyst | México", "Ciudad de México, México"),
    ("Analytics Engineer", "Santiago, Chile"),
])
def test_outras_estrangeiras_do_corpus(titulo, local):
    assert avaliar_normalizado(normalizar(_vaga(titulo, local))).estado \
        is Elegibilidade.INELEGIVEL


@pytest.mark.parametrize("local", [
    "São Paulo, São Paulo, Brasil",
    "São Paulo, São Paulo",
    "Belo Horizonte, Minas Gerais",
    "Remoto",
    "",
])
def test_vaga_brasileira_ou_indeterminada_nao_e_descartada(local):
    """306 das 320 vagas da Gupy são brasileiras. Um falso positivo aqui custaria
    muito mais que os 6 descartes corretos."""
    a = avaliar_normalizado(normalizar(_vaga("Analista de Dados Pleno", local)))
    assert a.estado is not Elegibilidade.INELEGIVEL


def test_o_campo_estruturado_nao_apaga_o_sinal_textual():
    """Quando o texto já diz que aceita Brasil, o local estrangeiro não deve
    inverter a decisão — a vaga pode ser sediada fora e contratar daqui."""
    vaga = _vaga("Data Engineer", "Lisboa, Portugal",
                 "Vaga aberta para profissionais no Brasil, contratação PJ.")
    n = normalizar(vaga)
    assert "BR" in (n.get("work_location_country") or []) or \
        avaliar_normalizado(n).estado is not Elegibilidade.INELEGIVEL
