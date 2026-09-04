"""Filtro de senioridade do 4B: descarta abaixo, nunca acima.

`SENIORIDADE_ORDEM` existia desde o início sem nenhum consumidor — faltava
decidir a política, não escrever o código. A decisão saiu com o dado na mão:
das 151 vagas aprovadas da Gupy, 12 eram júnior, passo atrás para quem tem 2,2
anos e cargo de Coordenador, e abaixo da faixa pretendida de 7-10k.

Só o piso filtra. Vaga acima do nível continua passando de propósito: "5+ anos"
em anúncio brasileiro costuma ser aspiracional, e Especialista às vezes descreve
escopo, não tempo de casa.
"""
import pytest

from jobapplier.filters.post_filter import NIVEL_MINIMO, SENIORIDADE_ORDEM, apply

CONFIG = {"pretensao": {"minimo": 7000, "alvo": 9000, "maximo": 10000}}


def _passa(normalizado, config=CONFIG):
    return apply(normalizado, config)[0]


# ── O piso ────────────────────────────────────────────────────────────────────

def test_junior_e_descartada():
    ok, motivo = apply({"senioridade": "Junior", "titulo": "Analista Jr"}, CONFIG)
    assert not ok
    assert "senioridade abaixo do mínimo" in motivo


@pytest.mark.parametrize("nivel", ["Pleno", "Senior", "Especialista", "Gerente"])
def test_do_nivel_minimo_para_cima_passa(nivel):
    """Acima do nível não descarta: descartar custaria mais que a triagem deles."""
    assert _passa({"senioridade": nivel, "titulo": f"Analista {nivel}"})


def test_senioridade_desconhecida_nunca_descarta():
    """23 das 151 vagas não declaram nível no título. Presumir júnior nelas seria
    descarte cego — e o descarte silencioso é o erro mais caro deste filtro."""
    assert _passa({"titulo": "Analista de Dados"})
    assert _passa({"senioridade": None, "titulo": "Analista de Dados"})
    assert _passa({"senioridade": "", "titulo": "X"})
    assert _passa({"senioridade": "Nível novo que ninguém previu", "titulo": "X"})


def test_caixa_do_nivel_nao_importa():
    assert not _passa({"senioridade": "JUNIOR", "titulo": "X"})
    assert not _passa({"senioridade": "junior", "titulo": "X"})


# ── O escape pela faixa publicada ─────────────────────────────────────────────

def test_junior_que_paga_dentro_da_faixa_e_mantida():
    """Título e remuneração nem sempre andam juntos: 'Júnior' em empresa grande
    às vezes paga dentro da pretensão, e aí o rótulo é convenção interna. Quando
    a vaga publica quanto paga, o número decide — é evidência mais forte."""
    assert _passa({
        "senioridade": "Junior", "titulo": "Analista Jr",
        "descricao_resumida": "Faixa salarial de R$ 8.000 a R$ 11.000",
    })


def test_junior_que_paga_abaixo_da_faixa_e_descartada():
    ok, motivo = apply({
        "senioridade": "Junior", "titulo": "Analista Jr",
        "descricao_resumida": "Salário de R$ 3.500",
    }, CONFIG)
    assert not ok
    assert "faixa publicada abaixo da pretensão" in motivo


def test_topo_da_faixa_publicada_e_o_que_conta():
    """'R$ 6.000 a R$ 9.000' é negociável para quem quer 7.000. Usar o piso do
    anúncio jogaria fora vaga viável."""
    assert _passa({
        "senioridade": "Junior", "titulo": "Jr",
        "descricao_resumida": "De R$ 6.000 a R$ 9.000",
    })


def test_sem_pretensao_configurada_o_escape_nao_se_aplica():
    """Sem faixa do usuário não há com que comparar; decide o título."""
    assert not apply({
        "senioridade": "Junior", "titulo": "Jr",
        "descricao_resumida": "Salário de R$ 9.000",
    }, {})[0]


def test_valor_de_beneficio_nao_conta_como_salario():
    """Medido no corpus: 'Engenheiro de Dados Pleno' com R$ 2.400 é vale-refeição.
    Valores fora da janela plausível são ignorados."""
    ok, _ = apply({
        "senioridade": "Junior", "titulo": "Jr",
        "descricao_resumida": "Vale-refeição de R$ 800 por mês",
    }, CONFIG)
    assert not ok, "R$ 800 não pode ser lido como faixa salarial"


# ── Extração de faixa ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("Salário de R$ 8.000 a R$ 11.000", (8000.0, 11000.0)),
    ("R$ 9.500,00 mensais", (9500.0, 9500.0)),
    ("R$ 7.000", (7000.0, 7000.0)),
    ("Vale-refeição de R$ 800", None),          # abaixo do piso plausível
    ("Faturamento de R$ 500.000.000", None),    # acima do teto plausível
    ("Sem informação salarial", None),
    ("", None),
])
def test_extracao_de_faixa_publicada(texto, esperado):
    from jobapplier.salario import extrair_faixa_publicada

    assert extrair_faixa_publicada(texto) == esperado


# ── Contrato ──────────────────────────────────────────────────────────────────

def test_o_mapa_de_senioridade_deixou_de_ser_letra_morta():
    """Existiu desde o início sem nenhum consumidor. Este teste falha se alguém
    remover o uso e o mapa voltar a ser decorativo."""
    import inspect

    from jobapplier.filters import post_filter

    fonte = inspect.getsource(post_filter)
    assert "SENIORIDADE_ORDEM[" in fonte or "SENIORIDADE_ORDEM.get" in fonte
    assert SENIORIDADE_ORDEM[NIVEL_MINIMO] == 2


def test_a_politica_e_so_piso_nao_teto():
    """Se alguém adicionar um teto no futuro, que seja decisão explícita e não
    efeito colateral: hoje Especialista e Gerente passam."""
    assert _passa({"senioridade": "Especialista", "titulo": "X"})
    assert _passa({"senioridade": "Gerente", "titulo": "X"})
