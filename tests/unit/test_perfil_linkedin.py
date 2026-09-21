"""Análise do perfil do LinkedIn: o mestre manda, e o mercado só sugere o que o
mestre sustenta.

O que estes testes protegem: divergência de fato entre perfil e currículo é
prioridade 1; tecnologia pedida pelo mercado só vira sugestão se estiver no
mestre (invariante 3); e a análise nunca toca rede ou banco.
"""
import pytest

from jobapplier import perfil_linkedin as mod

MESTRE = {
    "linkedin": "https://www.linkedin.com/in/fulano-de-tal/",
    "resumo_profissional": "Engenheiro de Dados com pipelines em Snowflake e Azure Data Factory.",
    "experiencias": [
        {"empresa": "Acme", "cargo": "Coordenador de Dados", "data_inicio": "08/2025",
         "data_fim": None},
        {"empresa": "Beta BI", "cargo": "Analista Pleno de BI", "data_inicio": "05/2024",
         "data_fim": "07/2025"},
    ],
    "formacao": [{"instituicao": "Faculdade X (FIAP)", "curso": "Tecnólogo",
                  "data_conclusao": "2025"}],
    "tecnologias": ["SQL", "Python", "Snowflake", "Azure Data Factory", "Databricks",
                    "Power BI", "Terraform"],
}

MERCADO = [("SQL", 120), ("Python", 110), ("Power BI", 80), ("Databricks", 60),
           ("Azure", 50), ("PySpark", 45), ("Snowflake", 30), ("Terraform", 10)]

PERFIL_BOM = {
    "titulo": "Coordenador de Dados | SQL, Python, Power BI, Databricks",
    "sobre": "Engenheiro de Dados com dois anos em pipelines de ingestão e transformação "
             "em Snowflake, Azure Data Factory e Databricks, com progressão de analista "
             "pleno a coordenação. Modelagem em camadas medallion, otimização de custo, "
             "infraestrutura como código em Terraform e CI/CD. Dashboards em Power BI.",
    "experiencias": [
        {"cargo": "Coordenador de Dados", "empresa": "Acme",
         "periodo": "ago de 2025 - o momento · 1 ano", "descricao": "Pipelines."},
        {"cargo": "Analista Pleno de BI", "empresa": "Beta BI",
         "periodo": "mai de 2024 - jul de 2025 · 1 ano 3 meses", "descricao": ""},
    ],
    "formacao": [{"instituicao": "FIAP", "curso": "Tecnólogo"}],
    "competencias": ["SQL", "Python", "Power BI", "Databricks", "Snowflake", "Terraform"],
}


def _areas(analise, prioridade=None):
    return [a.area for a in analise.ajustes if prioridade in (None, a.prioridade)]


# ── Identidade ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url, esperado", [
    ("https://www.linkedin.com/in/fulano-de-tal/", True),
    ("https://www.linkedin.com/in/Fulano-De-Tal?locale=en", True),
    ("https://www.linkedin.com/in/outra-pessoa/", False),
    ("https://www.linkedin.com/jobs/view/123", False),
    ("", False),
])
def test_so_o_proprio_perfil(url, esperado):
    assert mod.e_meu_perfil(url, MESTRE) is esperado


def test_sem_linkedin_no_mestre_nada_e_meu():
    assert mod.e_meu_perfil("https://www.linkedin.com/in/x/", {"linkedin": ""}) is False


# ── Perfil alinhado ───────────────────────────────────────────────────────────

def test_perfil_alinhado_nao_tem_ajuste_de_fato():
    analise = mod.analisar(PERFIL_BOM, MESTRE, MERCADO)
    assert not [a for a in analise.ajustes if a.prioridade == 1], analise.ajustes
    assert analise.cobertura[1] == len(MERCADO)


def test_lacuna_e_informacao_nao_ajuste():
    """PySpark: o mercado pede, o mestre não tem. Nunca vira 'adicione ao
    perfil' — isso seria o sistema afirmando o que o currículo não sustenta."""
    analise = mod.analisar(PERFIL_BOM, MESTRE, MERCADO)
    assert "PySpark" in analise.lacunas
    assert not any("PySpark" in a.sugestao for a in analise.ajustes)


# ── Fatos ─────────────────────────────────────────────────────────────────────

def test_cargo_divergente_e_prioridade_1():
    perfil = {**PERFIL_BOM, "experiencias": [
        dict(PERFIL_BOM["experiencias"][0], cargo="Head de Dados"),
        PERFIL_BOM["experiencias"][1]]}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    a = next(x for x in analise.ajustes if "Cargo na Acme" in x.problema)
    assert a.prioridade == 1 and a.sugestao == "Coordenador de Dados"


def test_data_divergente_e_prioridade_1():
    perfil = {**PERFIL_BOM, "experiencias": [
        dict(PERFIL_BOM["experiencias"][0], periodo="jan de 2023 - o momento"),
        PERFIL_BOM["experiencias"][1]]}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    assert any("Data na Acme" in a.problema and a.prioridade == 1 for a in analise.ajustes)


def test_experiencia_do_mestre_ausente_no_perfil():
    perfil = {**PERFIL_BOM, "experiencias": PERFIL_BOM["experiencias"][:1]}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    a = next(x for x in analise.ajustes if "'Beta BI'" in x.problema)
    assert a.prioridade == 1 and "Analista Pleno de BI" in a.sugestao


def test_experiencia_so_no_linkedin_e_apontada_sem_sugestao():
    """Só no perfil: ou entra no mestre ou sai. A análise não escolhe."""
    perfil = {**PERFIL_BOM, "experiencias": PERFIL_BOM["experiencias"] + [
        {"cargo": "Estagiário", "empresa": "Gama", "periodo": "2022", "descricao": ""}]}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    a = next(x for x in analise.ajustes if "'Gama'" in x.problema)
    assert a.sugestao == ""


def test_formacao_ausente():
    perfil = {**PERFIL_BOM, "formacao": []}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    assert any(a.area == "fato" and "Tecnólogo" in a.problema for a in analise.ajustes)


# ── Vocabulário ───────────────────────────────────────────────────────────────

def test_tecnologias_ausentes_viram_um_ajuste_so():
    """Oito cartões 'adicione X' é lista de afazeres; um ajuste lista todas,
    com a contagem de vagas, e diz quais merecem o título."""
    perfil = {**PERFIL_BOM, "titulo": "Coordenador de Dados",
              "sobre": "Trabalho com dados.", "competencias": ["SQL", "Python"],
              "experiencias": [dict(e, descricao="") for e in PERFIL_BOM["experiencias"]]}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    voc = [a for a in analise.ajustes if a.area == "competencias"]
    assert len(voc) == 1 and voc[0].prioridade == 2
    assert "Power BI (80)" in voc[0].problema and "Databricks (60)" in voc[0].problema
    # Entre as 5 mais pedidas e fora do título: vão para os dois lugares.
    assert "no título" in voc[0].sugestao and "Power BI" in voc[0].sugestao
    # Terraform está fora do top 5: só em Competências.
    linha_titulo = voc[0].sugestao.split("\n")[1]
    assert "Terraform" not in linha_titulo


def test_canonizacao_evita_falso_ausente():
    """'powerbi' nas competências conta como Power BI."""
    perfil = {**PERFIL_BOM, "competencias": ["powerbi", "sql", "python", "databricks",
                                             "snowflake", "terraform"]}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    assert not any("Power BI" in a.problema for a in analise.ajustes)


# ── Régua ─────────────────────────────────────────────────────────────────────

def test_titulo_vazio_e_prioridade_1_com_sugestao_do_mestre():
    perfil = {**PERFIL_BOM, "titulo": ""}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    a = next(x for x in analise.ajustes if x.area == "titulo")
    assert a.prioridade == 1
    assert a.sugestao.startswith("Coordenador de Dados | ")
    # Só tecnologias que o mestre tem — PySpark é do mercado, não do candidato.
    assert "PySpark" not in a.sugestao


def test_titulo_sem_as_mais_pedidas_e_apontado():
    perfil = {**PERFIL_BOM, "titulo": "Entusiasta de dados"}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    assert any(a.area == "titulo" and a.prioridade == 2 for a in analise.ajustes)


def test_sobre_vazio_sugere_o_resumo_do_mestre():
    perfil = {**PERFIL_BOM, "sobre": ""}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    a = next(x for x in analise.ajustes if x.area == "sobre")
    assert a.prioridade == 1 and a.sugestao == MESTRE["resumo_profissional"]


def test_competencias_vazias_e_prioridade_1():
    perfil = {**PERFIL_BOM, "competencias": []}
    analise = mod.analisar(perfil, MESTRE, MERCADO)
    a = next(x for x in analise.ajustes
             if x.area == "competencias" and x.prioridade == 1)
    assert "Adicionar:" in a.sugestao and "PySpark" not in a.sugestao


def test_ajustes_saem_ordenados_por_prioridade():
    perfil = {**PERFIL_BOM, "titulo": "", "competencias": []}
    d = mod.analisar(perfil, MESTRE, MERCADO).como_dict()
    prioridades = [a["prioridade"] for a in d["ajustes"]]
    assert prioridades == sorted(prioridades)


# ── Persistência ──────────────────────────────────────────────────────────────

def test_grava_e_carrega_em_data(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ARQUIVO", tmp_path / "perfil_linkedin.json")
    registro = mod.gravar(PERFIL_BOM, MESTRE["linkedin"])
    assert registro["lido_em"]
    lido = mod.carregar()
    assert lido["perfil"]["titulo"] == PERFIL_BOM["titulo"]
    assert lido["url"] == MESTRE["linkedin"]


def test_sem_arquivo_carrega_none(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ARQUIVO", tmp_path / "nada.json")
    assert mod.carregar() is None


# ── URL do perfil no mestre ───────────────────────────────────────────────────

def _mestre_em(tmp_path, monkeypatch, conteudo):
    import json

    from jobapplier import paths

    arquivo = tmp_path / "resume.json"
    arquivo.write_text(json.dumps(conteudo), encoding="utf-8")
    monkeypatch.setattr(paths, "RESUME_JSON", arquivo)
    return arquivo


@pytest.mark.parametrize("entrada", [
    "https://www.linkedin.com/in/Fulano-De-Tal/?locale=pt_BR",
    "linkedin.com/in/fulano-de-tal",
    "  https://br.linkedin.com/in/fulano-de-tal//  ",
])
def test_gravar_url_normaliza_e_grava_no_mestre(tmp_path, monkeypatch, entrada):
    """Contato é fato do currículo: vai para `resume.json`, não para a config.
    E canônica, porque `?locale=pt` e barra dupla são a mesma página e
    quebrariam a comparação de slug."""
    import json

    arquivo = _mestre_em(tmp_path, monkeypatch, {"nome": "Fulano", "linkedin": ""})
    canonica = mod.gravar_url(entrada)
    assert canonica.lower() == "https://www.linkedin.com/in/fulano-de-tal/"
    gravado = json.loads(arquivo.read_text(encoding="utf-8"))
    assert gravado["linkedin"] == canonica
    assert gravado["nome"] == "Fulano"          # o resto do mestre fica intacto


@pytest.mark.parametrize("ruim", ["", "https://www.linkedin.com/jobs/view/1",
                                  "https://google.com", "fulano"])
def test_gravar_url_recusa_o_que_nao_e_perfil(tmp_path, monkeypatch, ruim):
    arquivo = _mestre_em(tmp_path, monkeypatch, {"linkedin": "antes"})
    with pytest.raises(ValueError):
        mod.gravar_url(ruim)
    assert '"antes"' in arquivo.read_text(encoding="utf-8")   # nada gravado
