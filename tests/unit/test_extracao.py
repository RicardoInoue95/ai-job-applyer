"""Normalização e scoring sem LLM.

Normalizar é extração, não julgamento — e é a etapa de maior volume, milhares de
vagas por ciclo. Estes testes são a garantia de que o caminho sem custo produz
dado utilizável, não um placeholder.
"""
import types

import pytest

from jobapplier import vocabulario as vocab
from jobapplier.agents.extracao import limpar_cargo, normalizar, pontuar


def vaga(titulo="Data Engineer", descricao="", localizacao="São Paulo, SP", empresa="Acme"):
    return types.SimpleNamespace(
        id=1, titulo=titulo, empresa=empresa,
        localizacao=localizacao, descricao=descricao,
    )


CURRICULO = {
    "nome": "Candidato",
    "localizacao": "São Paulo, SP",
    "tecnologias": ["Python", "SQL", "Snowflake", "Azure Data Factory", "Power BI"],
    "idiomas": [{"nome": "Inglês", "nivel": "Avançado"}],
    "experiencias": [{"empresa": "Fintech X", "cargo": "Analytics Engineer",
                      "descricao": ["Pipelines em Snowflake"], "tecnologias": ["Snowflake"]}],
}


# ── Vocabulário: reconhecimento de tecnologia ─────────────────────────────────

def test_reconhece_tecnologias_em_portugues_e_ingles():
    achadas = vocab.tecnologias_em("Experiência com Python, SQL e Apache Airflow")
    assert {"Python", "SQL", "Airflow"} <= set(achadas)


def test_fronteira_de_palavra_evita_falso_positivo():
    """'java' dentro de 'javascript' era o risco de casar por substring."""
    achadas = vocab.tecnologias_em("Stack de JavaScript e TypeScript")
    assert "Java" not in achadas
    assert "JavaScript" in achadas


def test_variantes_convergem_para_o_nome_canonico():
    for texto in ("power bi", "PowerBI", "POWER BI"):
        assert "Power BI" in vocab.tecnologias_em(texto)


def test_canonizar_normaliza_escrita_do_curriculo():
    assert vocab.canonizar("powerbi") == "Power BI"
    assert vocab.canonizar("  Azure Data Factory ") == "Azure Data Factory"


def test_canonizar_devolve_original_quando_desconhecida():
    assert vocab.canonizar("Ferramenta Interna XYZ") == "Ferramenta Interna XYZ"


def test_equivalencia_entre_ferramentas_do_mesmo_papel():
    assert vocab.sao_equivalentes("Azure Data Factory", "Airflow")
    assert vocab.sao_equivalentes("Power BI", "Tableau")
    assert vocab.sao_equivalentes("Snowflake", "BigQuery")


def test_ferramentas_de_papeis_diferentes_nao_sao_equivalentes():
    assert not vocab.sao_equivalentes("Power BI", "Airflow")
    assert not vocab.sao_equivalentes("Python", "Terraform")


# ── Extração de campos ────────────────────────────────────────────────────────

@pytest.mark.parametrize("titulo,esperado", [
    ("Engenheiro de Dados Sênior", "Senior"),
    ("Data Engineer Jr", "Junior"),
    ("Analista de BI Pleno", "Pleno"),
    ("Tech Lead de Dados", "Especialista"),
    ("Coordenador de Dados", "Gerente"),
    ("Data Engineer", "Desconhecida"),
])
def test_senioridade_vem_do_titulo(titulo, esperado):
    assert vocab.senioridade_em(titulo) == esperado


def test_titulo_tem_precedencia_sobre_descricao():
    """A descrição cita vários níveis; o título é o que está sendo contratado."""
    assert vocab.senioridade_em(
        "Analista de Dados Pleno",
        "Você reportará ao Engenheiro Sênior e apoiará o time júnior.",
    ) == "Pleno"


@pytest.mark.parametrize("texto,esperado", [
    ("Vaga 100% remota", "Remoto"),
    ("Modelo híbrido, 2x por semana", "Híbrido"),
    ("Trabalho presencial em SP", "Presencial"),
    ("Não informado", "Desconhecida"),
])
def test_modalidade(texto, esperado):
    assert vocab.modalidade_em(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("mínimo de 5 anos de experiência", 5),
    ("no mínimo 3 anos", 3),
    ("at least 4 years", 4),
    ("3+ anos atuando com dados", 3),
    ("de 2 a 4 anos de experiência", 2),
    ("7 anos de experiência em dados", 7),
    ("sem exigência de tempo", None),
])
def test_anos_exigidos(texto, esperado):
    assert vocab.anos_exigidos(texto) == esperado


def test_anos_pega_o_menor_quando_ha_faixa():
    """'3 a 5 anos' exige 3. Pegar o maior descartaria vaga elegível."""
    assert vocab.anos_exigidos("Entre 3 a 5 anos. Desejável 8 anos em cloud.") == 3


def test_anos_ignora_numero_implausivel():
    assert vocab.anos_exigidos("fundada em 1998, 2024 anos de história") is None


def test_ingles_exigido_versus_mencionado():
    assert vocab.idioma_em("Inglês avançado obrigatório") == "Inglês"
    # Menção sem nível não é exigência.
    assert vocab.idioma_em("Ambiente com material em inglês") == "Português"


def test_descricao_toda_em_ingles_indica_processo_em_ingles():
    texto = "About the role: you will build pipelines. Requirements: SQL. Nice to have: dbt."
    assert vocab.idioma_em(texto) == "Inglês"


def test_setor_detectado():
    assert vocab.setor_em("Nubank", "somos uma fintech de crédito") == "Fintech"
    assert vocab.setor_em("", "plataforma de e-commerce") == "Varejo"
    assert vocab.setor_em("", "texto sem setor") is None


def test_salario_extraido():
    assert vocab.salario_em("Salário de R$ 12.000,00 mensais").startswith("R$")
    assert vocab.salario_em("A combinar") is None


# ── limpar_cargo ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bruto,esperado", [
    ("Analytics Engineer (Remoto)", "Analytics Engineer"),
    ("Data Engineer [Urgente]", "Data Engineer"),
    ("Engenheiro de Dados - Remoto", "Engenheiro de Dados"),
    ("Data Engineer #48213", "Data Engineer"),
    ("Analista de BI - SP", "Analista de BI"),
    ("Data Engineer", "Data Engineer"),
])
def test_limpar_cargo(bruto, esperado):
    assert limpar_cargo(bruto) == esperado


def test_limpar_cargo_nunca_devolve_vazio():
    assert limpar_cargo("(Remoto)") == "(Remoto)"
    assert limpar_cargo("") == ""


# ── normalizar ────────────────────────────────────────────────────────────────

def test_normalizar_produz_todos_os_campos():
    n = normalizar(vaga(descricao="Python e SQL, 3 anos, remoto"))
    esperados = {"cargo", "senioridade", "tecnologias", "anos_experiencia_minimo",
                 "localizacao", "modalidade", "salario", "soft_skills",
                 "idioma_principal", "setor_empresa"}
    assert esperados <= set(n)


def test_normalizar_marca_a_origem():
    """Sem isto não há como comparar depois a qualidade dos dois caminhos."""
    assert normalizar(vaga())["_origem"] == "deterministica"


def test_normalizar_nunca_falha_com_campos_vazios():
    vazia = types.SimpleNamespace(id=1, titulo="", empresa="", localizacao="", descricao="")
    n = normalizar(vazia)
    assert n["tecnologias"] == []
    assert n["senioridade"] == "Desconhecida"


# ── pontuar ───────────────────────────────────────────────────────────────────

def _vaga_pontuavel(**norm):
    v = vaga()
    base = {"tecnologias": ["Python", "SQL"], "senioridade": "Pleno",
            "modalidade": "Remoto", "idioma_principal": "Português",
            "setor_empresa": None, "anos_experiencia_minimo": None,
            "localizacao": "São Paulo"}
    v.normalizado_json = {**base, **norm}
    return v


def test_score_no_intervalo_valido():
    r = pontuar(_vaga_pontuavel(), CURRICULO, anos_experiencia=4)
    assert 0 <= r["score"] <= 100


def test_cobertura_total_de_skills_pontua_o_peso_cheio():
    r = pontuar(_vaga_pontuavel(tecnologias=["Python", "SQL"]), CURRICULO, 4)
    assert r["breakdown"]["skills_tecnicas"] == 40.0
    assert r["hard_requirements_met"]


def test_tecnologia_ausente_entra_em_missing_required():
    r = pontuar(_vaga_pontuavel(tecnologias=["Python", "Kubernetes"]), CURRICULO, 4)
    assert r["missing_required"] == ["Kubernetes"]
    assert not r["hard_requirements_met"]


def test_equivalente_conta_menos_que_identico():
    """Currículo tem Azure Data Factory; a vaga pede Airflow."""
    identico = pontuar(_vaga_pontuavel(tecnologias=["Snowflake"]), CURRICULO, 4)
    equivalente = pontuar(_vaga_pontuavel(tecnologias=["Airflow"]), CURRICULO, 4)
    assert equivalente["breakdown"]["skills_tecnicas"] < identico["breakdown"]["skills_tecnicas"]
    assert equivalente["breakdown"]["skills_tecnicas"] > 0


def test_experiencia_insuficiente_reduz_senioridade():
    r = pontuar(_vaga_pontuavel(anos_experiencia_minimo=8), CURRICULO, anos_experiencia=2)
    assert r["breakdown"]["senioridade"] < 20
    assert any("faltam" in g for g in r["gaps"])


def test_vaga_em_ingles_sem_idioma_no_curriculo_zera_o_criterio():
    sem_idioma = {**CURRICULO, "idiomas": []}
    r = pontuar(_vaga_pontuavel(idioma_principal="Inglês"), sem_idioma, 4)
    assert r["breakdown"]["idioma"] == 0.0


def test_ingles_avancado_pontua_cheio():
    r = pontuar(_vaga_pontuavel(idioma_principal="Inglês"), CURRICULO, 4)
    assert r["breakdown"]["idioma"] == 15.0


def test_presencial_em_outra_cidade_zera_localizacao():
    r = pontuar(
        _vaga_pontuavel(modalidade="Presencial", localizacao="Recife, PE"),
        CURRICULO, 4,
    )
    assert r["breakdown"]["localizacao"] == 0.0


def test_remoto_pontua_cheio_independente_da_cidade():
    r = pontuar(_vaga_pontuavel(modalidade="Remoto", localizacao="Recife, PE"), CURRICULO, 4)
    assert r["breakdown"]["localizacao"] == 10.0


def test_confianca_cai_quando_a_vaga_informa_pouco():
    rica = pontuar(_vaga_pontuavel(setor_empresa="Fintech"), CURRICULO, 4)
    pobre = pontuar(
        _vaga_pontuavel(tecnologias=[], senioridade="Desconhecida",
                        modalidade="Desconhecida", idioma_principal="Desconhecida"),
        CURRICULO, 4,
    )
    assert pobre["confidence"] < rica["confidence"]


def test_vaga_sem_tecnologia_nao_e_penalizada_como_incompativel():
    """Falta de informação não é evidência de incompatibilidade."""
    r = pontuar(_vaga_pontuavel(tecnologias=[]), CURRICULO, 4)
    assert r["breakdown"]["skills_tecnicas"] == 20.0


def test_formato_compativel_com_o_scorer_por_llm():
    r = pontuar(_vaga_pontuavel(), CURRICULO, 4)
    for chave in ("score", "breakdown", "motivos_positivos", "gaps", "resumo",
                  "perfil_base_sugerido"):
        assert chave in r
    assert set(r["breakdown"]) == {"skills_tecnicas", "senioridade", "setor",
                                   "idioma", "localizacao"}


@pytest.mark.parametrize("cargo,tecnologias,esperado", [
    ("Analytics Engineer", ["dbt"], "analytics_engineer"),
    ("Analista de BI", ["Power BI"], "bi_analyst"),
    ("Engenheiro de Dados", ["Airflow", "Spark"], "data_engineer"),
    ("Cloud Data Engineer", ["Terraform", "AWS"], "cloud_data_engineer"),
])
def test_perfil_base_sugerido(cargo, tecnologias, esperado):
    v = _vaga_pontuavel(tecnologias=tecnologias, cargo=cargo)
    assert pontuar(v, CURRICULO, 4)["perfil_base_sugerido"] == esperado


# ── Despacho: com e sem client ────────────────────────────────────────────────

def test_normalize_sem_client_usa_caminho_deterministico():
    from jobapplier.agents.normalizer import normalize

    assert normalize(vaga(descricao="Python"))["_origem"] == "deterministica"


def test_score_sem_client_usa_caminho_deterministico():
    from jobapplier.agents.scorer import score

    assert score(_vaga_pontuavel(), CURRICULO)["_origem"] == "deterministica"


def test_cover_letter_sem_client_e_factual():
    from jobapplier.agents.cover_letter import generate

    carta = generate(CURRICULO, _vaga_pontuavel())
    assert "Candidato" in carta
    assert "Python" in carta


def test_optimize_sem_client_reordena_sem_reescrever():
    from jobapplier.agents.resume_optimizer import optimize

    r = optimize(CURRICULO, _vaga_pontuavel(tecnologias=["Power BI"]))
    otimizado = r["perfil_otimizado"]
    assert otimizado["tecnologias"][0] == "Power BI"
    # Mesmas tecnologias, só reordenadas: nada inventado, nada removido.
    assert set(otimizado["tecnologias"]) == set(CURRICULO["tecnologias"])


def test_ollama_esta_registrado_e_dispensa_chave():
    from jobapplier import llm

    assert "ollama" in llm.PROVEDORES
    assert "ollama" in llm.SEM_CHAVE
    assert llm.chave_do_provedor("ollama") == "local"
