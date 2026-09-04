"""O modo sombra não pode gastar a cota de tentativas.

`MAX_TENTATIVAS_VAGA` existe para parar de martelar uma plataforma que falha.
Simulação nunca chega na plataforma — contá-la queima a cota sem tentar nada.

Custou caro: com o agendador a cada 15 min, três ciclos de sombra inutilizavam
a vaga **para sempre**. Aconteceu com as duas de maior score da fila (93,6 e
88,0), que nunca tocaram o Greenhouse e chegaram a `tentativas=3`.
"""
import pytest

from jobapplier.database.connection import get_session
from jobapplier.database.models import Vaga
from jobapplier.safety import guard

pytestmark = pytest.mark.db


@pytest.fixture
def vaga():
    with get_session() as s:
        v = Vaga(titulo="[teste] lease", empresa="[teste]", plataforma="greenhouse",
                 link="https://exemplo.test/[teste]-lease", descricao="x",
                 hash="hash-teste-lease", status="aprovada", tentativas=0)
        s.add(v)
        s.flush()
        vid = v.id
    yield vid
    with get_session() as s:
        alvo = s.get(Vaga, vid)
        if alvo is not None:
            s.delete(alvo)


def _tentativas(vid):
    with get_session() as s:
        return s.get(Vaga, vid).tentativas


def _soltar(vid):
    guard.liberar_lease(vid, "aprovada")


def test_modo_sombra_nao_gasta_tentativa(vaga):
    for _ in range(5):
        assert guard.adquirir_lease(vaga, dono="teste", conta_tentativa=False)
        _soltar(vaga)
    assert _tentativas(vaga) == 0


def test_envio_real_gasta_tentativa(vaga):
    assert guard.adquirir_lease(vaga, dono="teste")
    _soltar(vaga)
    assert _tentativas(vaga) == 1


def test_o_teto_continua_valendo_para_envio_real(vaga):
    """A correção não pode afrouxar a guarda que ela ajusta (invariante 10)."""
    for _ in range(guard.MAX_TENTATIVAS_VAGA):
        assert guard.adquirir_lease(vaga, dono="teste")
        _soltar(vaga)
    assert not guard.adquirir_lease(vaga, dono="teste")
    # E nem a sombra passa depois do teto: a vaga está esgotada de verdade.
    assert not guard.adquirir_lease(vaga, dono="teste", conta_tentativa=False)
