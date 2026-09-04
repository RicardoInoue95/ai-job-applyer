"""Currículo em português para vaga em inglês perde no parsing do ATS.

E perde em silêncio: o PDF sai correto, os termos simplesmente não casam, e não
há erro em lugar nenhum. Das 11.870 vagas coletadas, 3.980 títulos do Greenhouse
estão em inglês contra 439 em português — e Nubank, iFood e QuintoAndar publicam
em inglês mesmo para vagas em São Paulo.

A detecção é por palavra funcional, não por dicionário técnico: "data",
"pipeline" e "Snowflake" aparecem nos dois idiomas.
"""
import pytest

from jobapplier import idioma

VAGA_PT = """
Estamos em busca de uma pessoa Engenheira de Dados para atuar na construção de
pipelines em nuvem. Você será responsável por integrar fontes de dados, modelar
camadas e apoiar as áreas de negócio com informação confiável. É desejável
experiência com Snowflake e Python, e conhecimento de modelagem dimensional.
Oferecemos trabalho híbrido em São Paulo, com benefícios e plano de carreira.
"""

VAGA_EN = """
We are looking for a Data Engineer to join our team and help us build reliable
data pipelines in the cloud. You will be responsible for integrating sources,
modeling layers and supporting business teams with trustworthy information.
Experience with Snowflake and Python is required, and knowledge of dimensional
modeling is a plus. This role is hybrid and based in Sao Paulo.
"""


def test_vaga_em_portugues():
    assert idioma.detectar(VAGA_PT) == "pt"


def test_vaga_em_ingles():
    assert idioma.detectar(VAGA_EN) == "en"


def test_termo_tecnico_nao_decide():
    """Um texto só de stack não é inglês — "Snowflake, Python, ETL, Databricks"
    aparece igual nos dois idiomas. Contar termo técnico classificaria toda vaga
    brasileira como inglesa."""
    assert idioma.detectar("Snowflake Python ETL Databricks Airflow "
                           "Terraform Docker Kubernetes Spark dbt Kafka "
                           "PostgreSQL MongoDB Redis GraphQL "
                           "Power BI Tableau Looker Metabase "
                           "Azure AWS GCP Snowflake Databricks") == "indefinido"


def test_texto_curto_nao_decide():
    """Título sozinho tem ~6 palavras e quase nenhuma funcional. Chutar ali
    erraria muito, e o erro seria invisível."""
    assert idioma.detectar("Engenheiro de Dados Pleno") == "indefinido"
    assert idioma.detectar("Senior Data Engineer") == "indefinido"


def test_vazio_e_indefinido():
    assert idioma.detectar("") == "indefinido"
    assert idioma.detectar("", None, "  ") == "indefinido"


def test_bilingue_fica_indefinido():
    """Vaga que mistura os dois é genuinamente ambígua. Forçar um idioma seria
    pior que admitir a dúvida — o currículo sairia no idioma errado com
    convicção."""
    misto = (VAGA_PT[:280] + " " + VAGA_EN[:280])
    assert idioma.detectar(misto) == "indefinido"


def test_da_vaga_junta_titulo_e_descricao():
    from types import SimpleNamespace

    vaga = SimpleNamespace(titulo="Data Engineer", descricao=VAGA_EN)
    assert idioma.da_vaga(vaga) == "en"


def test_da_vaga_sem_campos_nao_quebra():
    from types import SimpleNamespace

    assert idioma.da_vaga(SimpleNamespace()) == "indefinido"
    assert idioma.da_vaga(SimpleNamespace(titulo=None, descricao=None)) == "indefinido"


# ── Instrução de prompt ───────────────────────────────────────────────────────

@pytest.mark.parametrize("codigo,esperado", [("pt", "português"), ("en", "inglês")])
def test_instrucao_nomeia_o_idioma(codigo, esperado):
    assert esperado in idioma.instrucao_para(codigo)


def test_instrucao_proibe_traduzir_o_que_precisa_bater():
    """Traduzir "Coordenador de Dados" para "Data Coordinator" criaria
    divergência com o LinkedIn e com o registro formal — e divergência de cargo
    é o descarte mais barato que existe."""
    txt = idioma.instrucao_para("en")
    for termo in ("empresa", "cargo formal", "tecnologia", "datas"):
        assert termo in txt


def test_indefinido_nao_instrui_nada():
    """Sem certeza do idioma, não force nenhum — o currículo base já está num."""
    assert idioma.instrucao_para("indefinido") == ""
    assert idioma.instrucao_para("") == ""


# ── Aviso de descompasso ──────────────────────────────────────────────────────

def test_avisa_quando_vaga_e_curriculo_divergem():
    aviso = idioma.descompasso("en", "pt")
    assert "inglês" in aviso and "português" in aviso


def test_nao_avisa_quando_batem():
    assert idioma.descompasso("pt", "pt") == ""


def test_nao_avisa_quando_indefinido():
    """Indefinido não é descompasso — é ausência de informação."""
    assert idioma.descompasso("indefinido") == ""
    assert idioma.descompasso("") == ""


# ── Contrato com o otimizador ─────────────────────────────────────────────────

def test_otimizador_passa_o_idioma_ao_prompt():
    """Sem isto o modelo escreve sempre em português, mesmo para vaga em inglês
    — e o descompasso não deixa rastro."""
    import inspect

    from jobapplier.agents.resume_optimizer import optimize

    fonte = inspect.getsource(optimize)
    assert "instrucao_para" in fonte
    assert "descompasso" in fonte, "o caminho sem LLM precisa avisar"


def test_aviso_so_no_caminho_sem_llm():
    """Com modelo, a instrução resolve e o aviso seria ruído."""
    import inspect

    from jobapplier.agents.resume_optimizer import optimize

    fonte = inspect.getsource(optimize)
    sem_llm = fonte[fonte.index("if client is None:"):]
    assert "descompasso" in sem_llm[:600]
