"""Leitura de campos da extensão, contra o formulário real da Gupy.

Esta é a camada que pega quebra de seletor, e a Gupy é o caso mais duro: o
rótulo da pergunta não vive num `<label for=>` como no Greenhouse — vive no
`<legend>` do fieldset, ou num atributo `label=` do próprio input. E o `id` é
`react-aria2452456307-25`, regerado a cada render: quem ancorar nele quebra na
primeira visita.

A fixture veio de uma candidatura real, reduzida à estrutura e sem dado pessoal.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

CAMPOS_JS = (Path(__file__).resolve().parents[2] / "extensao" / "campos.js"
             ).read_text(encoding="utf-8")


@pytest.fixture
def pagina(carregar_fixture):
    p = carregar_fixture("gupy_dados_adicionais.html")
    p.add_script_tag(content=CAMPOS_JS)
    return p


def test_le_a_pergunta_do_legend(pagina):
    """Na Gupy o enunciado do grupo de radio vive no <legend>. Sem isso, todo
    campo de radio viria sem rótulo e a API não teria o que responder."""
    campos = pagina.evaluate("lerCampos()")
    rotulos = [c["label"] for c in campos]
    assert any("indicou você para esta vaga" in r for r in rotulos), rotulos
    assert any("trabalha na empresa" in r for r in rotulos), rotulos


def test_le_a_pergunta_do_atributo_label(pagina):
    """O select da Gupy traz o rótulo num atributo `label=` no próprio input —
    forma que nenhuma outra plataforma do acervo usa."""
    campos = pagina.evaluate("lerCampos()")
    assert any("Onde você encontrou essa vaga" in c["label"] for c in campos)


def test_ancoragem_e_por_name_e_nunca_por_id(pagina):
    """`react-aria2452456307-25` é regerado a cada render."""
    campos = pagina.evaluate("lerCampos()")
    for c in campos:
        assert "react-aria" not in c["seletor"], c
    com_name = [c for c in campos if c["seletor"].startswith("[name=")]
    assert com_name, "nenhum campo ancorado por name"


def test_opcao_de_radio_nao_herda_o_enunciado(pagina):
    """O texto da opção fica no <label> que envolve o radio; o <legend> é a
    pergunta. Confundir os dois faria toda opção virar "Alguém que trabalha…"."""
    campos = pagina.evaluate("lerCampos()")
    radios = [c for c in campos if c["opcoes"]]
    assert radios, "nenhum campo com opções"
    for c in radios:
        for o in c["opcoes"]:
            assert o["label"] != c["label"], (c["label"], o)


def test_campo_sem_rotulo_e_ignorado(pagina):
    """Sem enunciado não há como decidir resposta. Mandar para a API um campo
    anônimo produziria um chute — invariante 3."""
    campos = pagina.evaluate("lerCampos()")
    assert all(c["label"].strip() for c in campos)


def test_nao_devolve_campo_ja_preenchido(pagina):
    """Sobrescrever o que a plataforma preencheu é dado velho por cima de dado
    certo — foi assim que o LinkedIn anexava o currículo da vaga anterior."""
    pagina.evaluate("""() => {
        const i = document.createElement('input');
        i.name = 'jaTem'; i.value = 'valor existente';
        const l = document.createElement('label');
        l.textContent = 'Campo já preenchido'; l.appendChild(i);
        document.querySelector('form').appendChild(l);
    }""")
    campos = pagina.evaluate("lerCampos()")
    assert not [c for c in campos if c["label"] == "Campo já preenchido"]


def _sem_comentarios(js: str) -> str:
    """JavaScript sem `//` e sem `/* */`.

    Existe porque o cabeçalho de `campos.js` **nomeia** as regras que ficam no
    Python — pretensão, CPF, pergunta sensível — para explicar por que não estão
    ali. Procurar essas palavras no arquivo inteiro reprovaria justamente a
    documentação honesta. É a sexta vez nesta base que uma checagem de substring
    briga com um comentário; a regra é olhar código, não prosa.
    """
    import re as _re

    sem_bloco = _re.sub(r"/\*.*?\*/", "", js, flags=_re.S)
    # Só comentário de linha inteira: cortar todo `//` engoliria `http://`.
    return "\n".join("" if linha.lstrip().startswith("//") else linha
                     for linha in sem_bloco.splitlines())


def test_o_script_nao_decide_nada():
    """A política de resposta vive no Python, com teste. Uma segunda cópia em
    JavaScript divergiria — e é a extensão que preenche formulário de verdade."""
    codigo = _sem_comentarios(CAMPOS_JS).lower()
    proibido = ("cpf", "salario", "pretens", "raça", "raca", "genero",
                "afirmativa", "linkedin.com/in")
    for termo in proibido:
        assert termo not in codigo, (
            f"'{termo}' no código de campos.js: decisão vazou para o cliente")
