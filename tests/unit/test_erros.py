"""O catálogo de erros: código estável, ação obrigatória, forma única.

Quatro superfícies falavam quatro línguas — string solta na API, texto no
aviso da extensão, `st.error` nas páginas, traceback no terminal. O catálogo
existe para que erro seja identificável por programa. Estes testes garantem que
ele continue sendo: código sem repetição, toda entrada com o que fazer, e a API
sem voltar a escrever mensagem fora dele.
"""
import re
from pathlib import Path

from jobapplier import erros

RAIZ = Path(__file__).resolve().parents[2]


def test_codigos_sao_unicos_e_estaveis():
    codigos = [e.codigo for e in erros.CATALOGO.values()]
    assert len(codigos) == len(set(codigos))
    # kebab-case, minúsculo, sem acento: é o que atravessa JSON, JS e log.
    for c in codigos:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", c), c


def test_toda_entrada_diz_o_que_fazer():
    """Erro que não diz o que fazer transfere o trabalho para quem está cansado."""
    for e in erros.CATALOGO.values():
        assert e.titulo and e.detalhe and e.acao, e.codigo
        assert not e.titulo.endswith("."), f"{e.codigo}: título com ponto final"


def test_como_dict_junta_o_caso_ao_generico():
    d = erros.VAGA_INEXISTENTE.como_dict("(id 42)")
    assert d["codigo"] == "vaga-inexistente"
    assert d["detalhe"].endswith("(id 42)")
    assert set(d) == {"codigo", "titulo", "detalhe", "acao", "auto", "familia"}


def test_api_nao_escreve_erro_fora_do_catalogo():
    """`{"erro": "texto"}` era como a API respondia. Voltar a isso quebra o
    contrato com a extensão e o painel, que leem `erro.codigo`."""
    fonte = (RAIZ / "jobapplier" / "api.py").read_text(encoding="utf-8")
    assert not re.search(r'\{"erro":\s*"', fonte), "string solta em api.py"


def test_por_codigo():
    assert erros.por_codigo("banco-fora") is erros.BANCO_FORA
    assert erros.por_codigo("nao-existe") is None
