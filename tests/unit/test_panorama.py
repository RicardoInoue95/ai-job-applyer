"""A classificação de barreira de envio, que é o que o quadro afirma.

Existe porque a alternativa foi medida e reprovada: reCAPTCHA parecia o atalho
para saber quais boards deixam a automação concluir, e está em 17 de 23 —
**incluindo os dois onde o envio comprovadamente funcionou**. Sem sinal
pré-envio, o mapa só se constrói com desfecho real, e então a regra que
transforma desfecho em conclusão precisa estar certa.
"""
import sys
from collections import Counter
from pathlib import Path

import pytest

from jobapplier.tempo import de_timestamp

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from panorama import classificar_barreira

#: Naive-UTC, como as colunas do banco (ver jobapplier/tempo.py). Construídos
#: por `de_timestamp` em vez de `datetime(...)` para não afirmar um fuso que a
#: coluna não tem.
JUNHO = de_timestamp(1782313200)    # 24/06/2026
AGOSTO = de_timestamp(1787595000)   # 24/08/2026


def test_envio_confirmado_marca_o_board():
    enviou, bloqueou, ultimo, _ = classificar_barreira(
        [("xpinc", "enviada_confirmada", JUNHO)], Counter())
    assert enviou == {"xpinc"}
    assert not bloqueou
    assert ultimo == JUNHO


def test_status_legado_tambem_conta_como_prova():
    """As 10 candidaturas históricas foram gravadas como 'enviada', antes da
    mudança de vocabulário. Ignorá-las jogaria fora a única prova que existe."""
    enviou, _, _, _ = classificar_barreira(
        [("c6bank", "enviada", JUNHO)], Counter())
    assert enviou == {"c6bank"}


def test_verificacao_marca_bloqueio():
    _, bloqueou, _, _ = classificar_barreira(
        [("adyen", "aguardando_verificacao", AGOSTO)], Counter())
    assert bloqueou == {"adyen"}


def test_bloqueio_vence_envio_antigo():
    """Um board que enviava e passou a exigir código é a mudança que o quadro
    existe para flagrar. Listá-lo como 'envio ok' por um sucesso de dois meses
    atrás esconderia exatamente isso."""
    enviou, bloqueou, _, _ = classificar_barreira(
        [("c6bank", "enviada", JUNHO),
         ("c6bank", "aguardando_verificacao", AGOSTO)], Counter())
    assert bloqueou == {"c6bank"}
    assert "c6bank" not in enviou


def test_ultimo_envio_e_o_mais_recente():
    _, _, ultimo, _ = classificar_barreira(
        [("xpinc", "enviada", JUNHO), ("c6bank", "enviada", AGOSTO)], Counter())
    assert ultimo == AGOSTO


@pytest.mark.parametrize("ruido", ["falha_automacao", "simulada",
                                   "revisao_manual", "erro"])
def test_desfecho_sem_prova_nao_classifica(ruido):
    """Simulada não prova nada — o modo sombra não chega a submeter. E falha
    técnica não distingue 'o board recusa' de 'o seletor quebrou'."""
    enviou, bloqueou, _, _ = classificar_barreira(
        [("stripe", ruido, JUNHO)], Counter())
    assert not enviou and not bloqueou


def test_conta_a_fila_dos_boards_nao_medidos():
    """O número que importa: quanto da fila está em terreno desconhecido."""
    _, _, _, desconhecidas = classificar_barreira(
        [("adyen", "aguardando_verificacao", AGOSTO),
         ("xpinc", "enviada", JUNHO)],
        Counter({"adyen": 9, "xpinc": 4, "stripe": 8, "airbnb": 4}))
    assert desconhecidas == 12


def test_sem_desfecho_nenhum_tudo_e_desconhecido():
    enviou, bloqueou, ultimo, desconhecidas = classificar_barreira(
        [], Counter({"stripe": 8}))
    assert not enviou and not bloqueou and ultimo is None
    assert desconhecidas == 8


def test_data_ausente_nao_quebra():
    """Linha antiga do banco pode não ter `criado_em`."""
    enviou, _, ultimo, _ = classificar_barreira(
        [("xpinc", "enviada", None)], Counter())
    assert enviou == {"xpinc"}
    assert ultimo is None
