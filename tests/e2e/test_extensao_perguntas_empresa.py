"""A etapa de perguntas da empresa na Gupy — onde 152 candidaturas morreram.

É o formulário mais hostil do acervo, e por um motivo específico: **não há
rótulo em lugar nenhum dos que os outros usam**. Sem `<label for>`, sem
`<legend>`, sem `label=`, sem `aria-labelledby`. O enunciado é um `<h3>` irmão
anterior, e a única coisa que o liga ao campo é a posição na árvore.

O custo de errar aqui foi medido no navegador real: as seis perguntas de
verdade — RG, órgão emissor, nome da mãe, nome do pai, naturalidade e pretensão
— saíam sem rótulo e eram descartadas pela regra "campo sem rótulo é ignorado".
Sobravam os checkboxes, cujo `<label>` ancestral é o texto da OPÇÃO, e o aviso
anunciava "UOL · PagBank · UOL EdTech" como se fossem três perguntas.

A fixture veio dessa página, sem dado pessoal e sem CSS.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

CAMPOS_JS = (Path(__file__).resolve().parents[2] / "extensao" / "campos.js"
             ).read_text(encoding="utf-8")

#: As seis que importam, na ordem em que a página as apresenta.
PERGUNTAS = [
    "RG",
    "Órgão e Estado de emissão do RG",
    "Nome da mãe",
    "Nome do pai",
    "Naturalidade (cidade e estado de nascimento)",
    "Pretensão Salarial",
]


@pytest.fixture
def pagina(carregar_fixture):
    p = carregar_fixture("gupy_perguntas_empresa.html")
    p.add_script_tag(content=CAMPOS_JS)
    return p


def test_le_a_pergunta_do_cabecalho_acima(pagina):
    """Sem isto os seis campos vinham sem rótulo e eram descartados: a extensão
    lia sete "perguntas" e nenhuma era pergunta."""
    rotulos = [c["label"] for c in pagina.evaluate("lerCampos()")]
    for esperada in PERGUNTAS:
        assert any(esperada in r for r in rotulos), (esperada, rotulos)


def test_a_numeracao_e_o_asterisco_saem_do_rotulo(pagina):
    """O `<h3>` diz "6. Pretensão Salarial  *". A política do Python casa por
    substring, então lixo no rótulo não quebra — mas o rótulo também vira texto
    de aviso para o candidato ler."""
    rotulos = [c["label"] for c in pagina.evaluate("lerCampos()")]
    assert "Pretensão Salarial" in rotulos, rotulos
    assert not [r for r in rotulos if r[:1].isdigit() and r[1:2] in ".)"]
    assert not [r for r in rotulos if r.endswith("*")]


def test_opcao_de_checkbox_nao_vira_pergunta(pagina):
    """"UOL", "PagBank" e "UOL EdTech" são opções de uma pergunta só."""
    campos = pagina.evaluate("lerCampos()")
    rotulos = [c["label"] for c in campos]
    for opcao in ("UOL", "PagBank", "UOL EdTech"):
        assert opcao not in rotulos, f"{opcao!r} entrou como pergunta: {rotulos}"


def test_as_duas_perguntas_de_checkbox_ficam_separadas(pagina):
    """Grupos diferentes (`2800745` e `2800746`) são perguntas diferentes, ainda
    que ambas falem do Grupo UOL. Agrupar por prefixo não pode fundi-las."""
    campos = pagina.evaluate("lerCampos()")
    com_opcoes = [c for c in campos if len(c["opcoes"]) > 1]
    assert len(com_opcoes) == 2, [c["label"] for c in com_opcoes]
    assert len({c["seletor"] for c in com_opcoes}) == 2


def test_checkboxes_do_mesmo_grupo_viram_um_campo_so(pagina):
    """A Gupy numera cada checkbox do grupo (`checkbox-2800745-0`, `-1`, …), e
    agrupar por `name` não agrupa nada."""
    campos = pagina.evaluate("lerCampos()")
    # "Grupo UOL" aparece em DUAS perguntas desta tela — "já trabalhou" e
    # "possui parentes". Filtrar por ele pegava as duas e o teste reprovava o
    # agrupamento correto.
    grupo = [c for c in campos if c["label"].startswith("Já trabalhou")]
    assert len(grupo) == 1, [c["label"] for c in campos]
    opcoes = [o["label"] for o in grupo[0]["opcoes"]]
    assert "UOL" in opcoes and "PagBank" in opcoes, opcoes
    assert len(opcoes) >= 2


def test_seletor_do_grupo_alcanca_todas_as_opcoes(pagina):
    """O seletor do campo agrupado precisa casar com os membros do grupo, senão
    `escrever()` não acha o que marcar."""
    campos = pagina.evaluate("lerCampos()")
    grupo = next(c for c in campos if c["label"].startswith("Já trabalhou"))
    achados = pagina.evaluate("(s) => document.querySelectorAll(s).length",
                              grupo["seletor"])
    assert achados == len(grupo["opcoes"]), (grupo["seletor"], achados)


def test_opcao_carrega_o_proprio_seletor(pagina):
    """Os checkboxes da Gupy não têm `value` — todos valem "on". Sem o seletor
    por opção, marcar por valor acertaria sempre o primeiro da lista."""
    campos = pagina.evaluate("lerCampos()")
    grupo = next(c for c in campos if c["label"].startswith("Já trabalhou"))
    for opcao in grupo["opcoes"]:
        assert opcao["seletor"], opcao
        assert pagina.evaluate("(s) => !!document.querySelector(s)", opcao["seletor"])


def test_nenhum_campo_ancorado_em_classe_de_styled_components(pagina):
    """`sc-bklklh` é hash regerado a cada build da Gupy, como o `react-aria` do
    id. Ancorar nele quebraria na primeira visita."""
    for c in pagina.evaluate("lerCampos()"):
        assert "sc-" not in c["seletor"], c
        assert "css-" not in c["seletor"], c
