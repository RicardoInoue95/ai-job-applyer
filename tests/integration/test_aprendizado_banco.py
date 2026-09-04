"""Ciclo completo do banco de respostas, contra Postgres.

O unitário cobre a política — onde uma resposta pode ser repetida. Aqui é o que
só o banco revela: unicidade, sobrescrita, apagamento e o contador que mede a
economia de tédio.
"""
import pytest

from jobapplier import aprendizado
from jobapplier.database.connection import get_session
from jobapplier.database.models import RespostaAprendida

pytestmark = pytest.mark.db

MAE = "Nome da mãe"


@pytest.fixture(autouse=True)
def limpar():
    """Cada teste começa e termina sem rastro: são dados de teste num banco de
    produção, e deixá-los faria a tela de revisão mostrar lixo."""
    def _apagar():
        with get_session() as s:
            (s.query(RespostaAprendida)
             .filter(RespostaAprendida.pergunta.like("%[teste]%")).delete(
                 synchronize_session=False))
    _apagar()
    yield
    _apagar()


def _registrar(pergunta, resposta, empresa=""):
    with get_session() as s:
        return aprendizado.registrar(s, pergunta, resposta, empresa)


def _consultar(pergunta, empresa=""):
    with get_session() as s:
        return aprendizado.consultar(s, pergunta, empresa)


def test_o_que_voce_digita_volta_na_proxima_vaga():
    """O ponto inteiro da funcionalidade: responder uma vez, não 230."""
    assert _registrar(f"{MAE} [teste]", "Maria Silva", "PagBank")
    assert _consultar(f"{MAE} [teste]", "Nubank") == "Maria Silva"


def test_a_mesma_pergunta_nao_vira_duas_entradas():
    """Sem a constraint, cada formulário criaria outra linha e a tela de revisão
    viraria uma lista de duplicatas."""
    _registrar(f"{MAE} [teste]", "Maria Silva", "PagBank")
    _registrar(f"{MAE} [teste]", "Maria Silva", "Nubank")
    with get_session() as s:
        achados = (s.query(RespostaAprendida)
                   .filter(RespostaAprendida.pergunta.like("%[teste]%")).all())
    assert len(achados) == 1, [a.pergunta for a in achados]


def test_corrigir_sobrescreve_em_vez_de_acumular():
    _registrar(f"{MAE} [teste]", "Maria Silva")
    _registrar(f"{MAE} [teste]", "Maria da Silva")
    assert _consultar(f"{MAE} [teste]") == "Maria da Silva"


def test_esvaziar_apaga_em_vez_de_gravar_vazio():
    """Limpar o campo é como você diz "não era isso". Gravar "" faria o banco
    responder nada em todo formulário seguinte, silenciosamente."""
    _registrar(f"{MAE} [teste]", "Maria Silva")
    _registrar(f"{MAE} [teste]", "   ")
    assert _consultar(f"{MAE} [teste]") is None


def test_pergunta_aberta_nao_vaza_entre_empresas():
    """A resposta escrita para uma empresa não pode ser oferecida a outra."""
    aberta = "Por que você quer trabalhar aqui? [teste]"
    _registrar(aberta, "Admiro a cultura de dados de vocês.", "PagBank")
    assert _consultar(aberta, "PagBank")
    assert _consultar(aberta, "Nubank") is None


def test_contador_mede_quantas_vezes_voce_nao_redigitou():
    """É o número que a tela de revisão mostra como economia — e a única prova
    de que a memória serviu para alguma coisa."""
    _registrar(f"{MAE} [teste]", "Maria Silva")
    for _ in range(3):
        _consultar(f"{MAE} [teste]")
    with get_session() as s:
        alvo = (s.query(RespostaAprendida)
                .filter(RespostaAprendida.pergunta.like("%[teste]%")).one())
        assert alvo.vezes_usada == 3
        assert alvo.usada_em is not None
