"""Regra do projeto: nenhum PDF sai sem render de inspeção e checagem de layout.

Currículos foram enviados a recrutadores com layout quebrado porque ninguém
olhava o resultado e nada verificava. Estes testes travam as duas metades da
regra e o defeito concreto que ocorreu.
"""
import json

import pytest

from jobapplier.agents.resume_optimizer import _normalizar_saida
from jobapplier.generators.pdf import (
    LayoutInvalidoError,
    generate_pdf,
    normalizar_itens,
)
from jobapplier.generators.preview import (
    gerar_preview_e_verificar,
    renderizar,
    verificar_layout,
)

CURRICULO = {
    "nome": "Ricardo Y. K. Inoue",
    "email": "info@exemplo.com",
    "linkedin": "linkedin.com/in/exemplo",
    "localizacao": "São Paulo, SP",
    "resumo_profissional": "Engenheiro de Dados com experiência em pipelines ETL/ELT.",
    "tecnologias": ["Python", "SQL", "Snowflake", "dbt", "Azure Data Factory"],
    "idiomas": [{"nome": "Português", "nivel": "Nativo"},
                {"nome": "Inglês", "nivel": "Avançado"}],
    "experiencias": [
        {
            "empresa": "Empresa A",
            "cargo": "Coordenador de Dados",
            "data_inicio": "08/2025",
            "data_fim": None,
            "descricao": [
                "Coordenação técnica de iniciativas de dados",
                "Construção de pipelines ETL/ELT em Snowflake",
                "Modelagem analítica em camadas bronze, silver e gold",
            ],
            "conquistas": ["Redução de custo de processamento"],
            "tecnologias": ["Snowflake", "SQL"],
        },
    ],
    "formacao": [{"instituicao": "FIAP", "curso": "Defesa Cibernética",
                  "data_conclusao": "2025", "em_andamento": True}],
    "certificacoes": [],
}


@pytest.fixture
def curriculo():
    return json.loads(json.dumps(CURRICULO))


# ── normalizar_itens: a defesa no limite da renderização ──────────────────────

def test_lista_passa_intacta():
    assert normalizar_itens(["a", "b"]) == ["a", "b"]


def test_string_simples_vira_lista_de_um():
    assert normalizar_itens("um parágrafo") == ["um parágrafo"]


def test_lista_serializada_como_string_e_desempacotada():
    """O defeito real: o LLM devolveu a lista como repr de string."""
    bruto = "['Coordenação técnica de dados', 'Construção de pipelines ETL']"
    assert normalizar_itens(bruto) == [
        "Coordenação técnica de dados",
        "Construção de pipelines ETL",
    ]


def test_lista_serializada_com_aspas_duplas():
    assert normalizar_itens('["um", "dois"]') == ["um", "dois"]


def test_string_que_apenas_comeca_com_colchete_nao_e_quebrada():
    assert normalizar_itens("[nota] texto normal") == ["[nota] texto normal"]


def test_vazios_viram_lista_vazia():
    for valor in (None, "", [], "   "):
        assert normalizar_itens(valor) in ([], [""]) or normalizar_itens(valor) == []


def test_itens_vazios_sao_descartados():
    assert normalizar_itens(["a", "", "  ", "b"]) == ["a", "b"]


def test_tupla_tambem_e_aceita():
    assert normalizar_itens(("a", "b")) == ["a", "b"]


# ── _normalizar_saida: a correção na origem ───────────────────────────────────

def test_normaliza_descricao_serializada_do_otimizador(curriculo):
    curriculo["experiencias"][0]["descricao"] = str(curriculo["experiencias"][0]["descricao"])
    saida = _normalizar_saida(curriculo)
    desc = saida["experiencias"][0]["descricao"]
    assert isinstance(desc, list)
    assert len(desc) == 3
    assert desc[0].startswith("Coordenação")


def test_normaliza_conquistas_e_tecnologias(curriculo):
    curriculo["experiencias"][0]["conquistas"] = "['Uma conquista']"
    curriculo["experiencias"][0]["tecnologias"] = "['Snowflake', 'SQL']"
    saida = _normalizar_saida(curriculo)
    exp = saida["experiencias"][0]
    assert exp["conquistas"] == ["Uma conquista"]
    assert exp["tecnologias"] == ["Snowflake", "SQL"]


def test_normalizar_saida_tolera_forma_inesperada():
    assert _normalizar_saida({"experiencias": "não é lista"})["experiencias"] == "não é lista"
    assert _normalizar_saida({"experiencias": [None, 42]})  # não deve levantar
    assert _normalizar_saida("nem é dict") == "nem é dict"


# ── A regra: gerar PDF sempre produz preview e verifica ───────────────────────

def test_pdf_valido_gera_preview(curriculo, tmp_path):
    pdf = generate_pdf(curriculo, tmp_path / "cv.pdf")
    assert pdf.exists()
    previews = sorted(tmp_path.glob("cv_p*.png"))
    assert previews, "a regra exige imagem de inspeção para todo PDF gerado"
    assert previews[0].stat().st_size > 5000, "PNG suspeito de estar vazio"


def test_pdf_valido_nao_tem_problema_de_layout(curriculo, tmp_path):
    pdf = generate_pdf(curriculo, tmp_path / "cv.pdf")
    assert verificar_layout(pdf) == []


def test_curriculo_de_uma_experiencia_cabe_em_uma_pagina(curriculo, tmp_path):
    generate_pdf(curriculo, tmp_path / "cv.pdf")
    assert len(sorted(tmp_path.glob("cv_p*.png"))) == 1


def test_estrutura_vazada_e_detectada_e_bloqueia(curriculo, tmp_path):
    """resumo_profissional é parágrafo simples — caminho sem normalização."""
    curriculo["resumo_profissional"] = str({"resumo": "Engenheiro", "anos": 6})

    with pytest.raises(LayoutInvalidoError) as info:
        generate_pdf(curriculo, tmp_path / "vazado.pdf")

    assert "estrutura_vazada" in str(info.value)
    # O arquivo e o preview continuam em disco, para inspeção do defeito.
    assert (tmp_path / "vazado.pdf").exists()
    assert sorted(tmp_path.glob("vazado_p*.png"))


def test_estrito_false_permite_inspecionar_o_defeito(curriculo, tmp_path):
    curriculo["resumo_profissional"] = str({"a": "b"})
    pdf = generate_pdf(curriculo, tmp_path / "cv.pdf", estrito=False)
    assert pdf.exists()
    assert any(p.tipo == "estrutura_vazada" for p in verificar_layout(pdf))


def test_preview_desligado_nao_gera_png(curriculo, tmp_path):
    generate_pdf(curriculo, tmp_path / "cv.pdf", preview=False)
    assert not sorted(tmp_path.glob("cv_p*.png"))


def test_descricao_serializada_nao_chega_quebrada_ao_pdf(curriculo, tmp_path):
    """Defesa em profundidade: mesmo sem passar pelo otimizador, o PDF sai certo."""
    curriculo["experiencias"][0]["descricao"] = str(curriculo["experiencias"][0]["descricao"])
    pdf = generate_pdf(curriculo, tmp_path / "cv.pdf")
    assert verificar_layout(pdf) == []


# ── preview: render e verificação ─────────────────────────────────────────────

def test_renderizar_aceita_destino_customizado(curriculo, tmp_path):
    pdf = generate_pdf(curriculo, tmp_path / "cv.pdf", preview=False)
    destino = tmp_path / "previews"
    imagens = renderizar(pdf, destino=destino)
    assert imagens and all(i.parent == destino for i in imagens)


def test_renderizar_pdf_inexistente_levanta(tmp_path):
    with pytest.raises(FileNotFoundError):
        renderizar(tmp_path / "nao_existe.pdf")


def test_gerar_preview_nunca_levanta_em_pdf_invalido(tmp_path):
    """Falha de inspeção não deve descartar um PDF; devolve o que conseguiu."""
    falso = tmp_path / "corrompido.pdf"
    falso.write_bytes(b"nao sou um pdf")
    imagens, problemas = gerar_preview_e_verificar(falso)
    assert imagens == []
    assert isinstance(problemas, list)


def test_dpi_maior_gera_imagem_maior(curriculo, tmp_path):
    pdf = generate_pdf(curriculo, tmp_path / "cv.pdf", preview=False)
    baixo = renderizar(pdf, destino=tmp_path / "baixo", dpi=72)[0]
    alto = renderizar(pdf, destino=tmp_path / "alto", dpi=150)[0]
    assert alto.stat().st_size > baixo.stat().st_size


# ── Idioma do documento ───────────────────────────────────────────────────────
# O conteúdo passou a ser traduzido (data/resume_en.json) e o documento não: o
# currículo em inglês saía com "RESUMO PROFISSIONAL", "Presente" e "Linguagens"
# nos rótulos. Para o recrutador lê como descuido; para o ATS, rótulo de seção é
# âncora de parsing.

CURRICULO_EN = {
    "nome": "Ricardo Y. K. Inoue",
    "email": "info@exemplo.com",
    "linkedin": "linkedin.com/in/exemplo",
    "localizacao": "São Paulo, Brazil",
    "resumo_profissional": "Data Engineer with two years of experience building "
                           "ETL/ELT pipelines in the cloud, and modeling the "
                           "layers that the business teams rely on every day.",
    "tecnologias": ["Python", "SQL", "Snowflake", "dbt", "Azure Data Factory"],
    "idiomas": [{"nome": "Portuguese", "nivel": "Native"},
                {"nome": "English", "nivel": "Advanced"}],
    "experiencias": [
        {
            "empresa": "Empresa A",
            "cargo": "Data Coordinator",
            "data_inicio": "08/2025",
            "data_fim": None,
            "descricao": [
                "Build ETL/ELT pipelines on Snowflake and Azure Data Factory, "
                "integrating the sources that the business teams depend on.",
                "Model bronze, silver and gold layers, separating raw ingestion "
                "from curated data for every new analysis that comes in.",
            ],
            "conquistas": ["Reduced processing cost"],
            "tecnologias": ["Snowflake", "SQL"],
        },
    ],
    "formacao": [{"instituicao": "FIAP", "curso": "Cyber Defense",
                  "data_conclusao": "2025", "em_andamento": False}],
    "certificacoes": [],
}


@pytest.fixture
def curriculo_en():
    return json.loads(json.dumps(CURRICULO_EN))


def _texto(pdf):
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        return "\n".join(p.extract_text() or "" for p in doc.pages).lower()


def test_curriculo_em_portugues_mantem_rotulos_em_portugues(curriculo, tmp_path):
    texto = _texto(generate_pdf(curriculo, tmp_path / "pt.pdf", preview=False))
    for rotulo in ("resumo profissional", "experiência profissional",
                   "competências técnicas", "formação acadêmica", "idiomas"):
        assert rotulo in texto, f"faltou '{rotulo}' no currículo em português"


def test_curriculo_em_ingles_traduz_os_rotulos(curriculo_en, tmp_path):
    texto = _texto(generate_pdf(curriculo_en, tmp_path / "en.pdf", preview=False))
    for rotulo in ("professional summary", "professional experience",
                   "technical skills", "education", "languages"):
        assert rotulo in texto, f"faltou '{rotulo}' no currículo em inglês"
    for vazado in ("resumo profissional", "experiência profissional",
                   "competências técnicas", "formação acadêmica"):
        assert vazado not in texto, f"'{vazado}' vazou no currículo em inglês"


def test_cargo_atual_em_ingles_nao_diz_presente(curriculo_en, tmp_path):
    """`data_fim` nulo virava "Presente" fixo, no meio de datas em inglês."""
    texto = _texto(generate_pdf(curriculo_en, tmp_path / "en.pdf", preview=False))
    assert "present" in texto
    assert "presente" not in texto


def test_categoria_de_tecnologia_segue_o_idioma(curriculo_en, tmp_path):
    texto = _texto(generate_pdf(curriculo_en, tmp_path / "en.pdf", preview=False))
    assert "languages" in texto
    assert "linguagens" not in texto


def test_idioma_explicito_vence_a_deteccao(curriculo, tmp_path):
    """Há caminho de reprocessamento que conhece a vaga melhor que o texto."""
    pdf = generate_pdf(curriculo, tmp_path / "forcado.pdf", preview=False,
                       idioma="en")
    assert "professional summary" in _texto(pdf)


@pytest.mark.parametrize("valor", ["es", "", "xx", None])
def test_idioma_desconhecido_cai_no_portugues(curriculo, tmp_path, valor):
    """Sem idioma suportado, o padrão do arquivo mestre. Documento em português
    para vaga em inglês é ruim; em inglês para recrutador brasileiro é pior."""
    pdf = generate_pdf(curriculo, tmp_path / f"{valor or 'nulo'}.pdf",
                       preview=False, idioma=valor)
    assert "resumo profissional" in _texto(pdf)


def test_texto_curto_nao_forca_ingles(tmp_path):
    """Currículo sem texto suficiente para decidir fica em português, não vira
    inglês por causa de uma lista de tecnologias que é igual nos dois idiomas."""
    magro = {"nome": "Fulano", "email": "a@b.c",
             "tecnologias": ["Python", "SQL", "Snowflake", "Airflow", "dbt"],
             "experiencias": [], "formacao": [], "certificacoes": []}
    pdf = generate_pdf(magro, tmp_path / "magro.pdf", preview=False)
    assert "competências técnicas" in _texto(pdf)


def test_curriculo_em_ingles_passa_na_checagem_ats(curriculo_en, tmp_path):
    """`SECOES_OBRIGATORIAS` só conhecia cabeçalho em português, e a falha é
    fechada: traduzir os rótulos reprovou o PDF em inglês inteiro, e nenhuma
    candidatura em inglês sairia. Este teste é o que impede a volta disso."""
    from jobapplier.generators.preview import verificar_ats

    pdf = generate_pdf(curriculo_en, tmp_path / "en.pdf", preview=False)
    ausentes = [p for p in verificar_ats(pdf) if p.tipo == "secao_ausente"]
    assert not ausentes, [p.mensagem for p in ausentes]


def test_curriculo_em_portugues_segue_passando_na_checagem_ats(curriculo, tmp_path):
    from jobapplier.generators.preview import verificar_ats

    pdf = generate_pdf(curriculo, tmp_path / "pt.pdf", preview=False)
    ausentes = [p for p in verificar_ats(pdf) if p.tipo == "secao_ausente"]
    assert not ausentes, [p.mensagem for p in ausentes]


# ── Equivalência de ferramenta ────────────────────────────────────────────────
# Metade da fila (248 de 499 vagas vivas) pede algo que o candidato não tem mas
# cuja ferramenta equivalente ele usa: AWS←Azure 89x, Airflow←ADF 82x,
# Tableau←Power BI 64x. Até aqui isso só existia no score e na ordenação — o
# documento escrevia "Azure", a vaga procurava "AWS", e ninguém fazia a ponte.

def test_equivalente_aparece_rotulado(curriculo, tmp_path):
    """"equivalente: AWS" é uma afirmação verdadeira; "AWS" solto na lista de
    tecnologias seria experiência inventada (invariante 3)."""
    curriculo["equivalencias"] = ["AWS", "Tableau"]
    texto = _texto(generate_pdf(curriculo, tmp_path / "eq.pdf", preview=False))
    assert "equivalente: aws" in texto
    assert "equivalente: tableau" in texto


def test_sem_equivalencias_nada_muda(curriculo, tmp_path):
    texto = _texto(generate_pdf(curriculo, tmp_path / "sem.pdf", preview=False))
    assert "equivalente" not in texto


def test_equivalente_fica_ao_lado_do_que_o_justifica():
    """"equivalente: Airflow" colado em "Azure Data Factory" explica a ponte
    sozinho. Numa linha distante, o leitor não liga uma coisa à outra."""
    from jobapplier.generators.pdf import _agrupar_equivalentes, _group_techs

    grupos = _group_techs(["Azure Data Factory", "Power BI"], "pt")
    onde = _agrupar_equivalentes(["Airflow", "Tableau"], "pt", grupos)
    assert "Airflow" in onde["Cloud & Big Data"], "ADF cai em Cloud pelo 'azure'"
    assert onde["Visualização & BI"] == ["Tableau"]


def test_equivalente_nunca_some(curriculo, tmp_path):
    """Categoria sem linha no currículo fazia a equivalência evaporar — foi
    assim que Tableau sumiu de um perfil sem Power BI."""
    from jobapplier.generators.pdf import _agrupar_equivalentes, _group_techs

    grupos = _group_techs(["Python", "Snowflake"], "pt")
    onde = _agrupar_equivalentes(["Tableau", "Airflow", "AWS"], "pt", grupos)
    colocados = [t for lista in onde.values() for t in lista]
    assert set(colocados) == {"Tableau", "Airflow", "AWS"}


def test_nenhum_termo_de_equivalencia_fica_sem_categoria():
    """Termo sem categoria some do PDF em silêncio. Airflow — a segunda ponte
    mais frequente, 82 vagas — sumia assim antes desta trava."""
    from jobapplier.generators.pdf import _TECH_GROUPS, _match_tech
    from jobapplier.vocabulario import EQUIVALENCIAS

    orfas = [t for grupo in EQUIVALENCIAS for t in grupo
             if not any(_match_tech(t, kw) for _, kws in _TECH_GROUPS for kw in kws)]
    assert not orfas, f"sem categoria no PDF: {sorted(orfas)}"


def test_rotulo_segue_o_idioma(curriculo_en, tmp_path):
    curriculo_en["equivalencias"] = ["AWS"]
    texto = _texto(generate_pdf(curriculo_en, tmp_path / "eq_en.pdf", preview=False))
    assert "equivalent: aws" in texto
    assert "equivalente:" not in texto
