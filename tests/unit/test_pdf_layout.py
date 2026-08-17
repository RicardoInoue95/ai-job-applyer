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
