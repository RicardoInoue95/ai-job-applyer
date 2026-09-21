"""O funil manual: o que você marca vira evento, o mais forte conta.

Sem banco: `por_vaga` e `resumo` são substituídos onde tocam o banco; o que se
testa é a regra — força dos desfechos, o que "aguardando" significa, e que
"sem resposta" desfaz.
"""
from jobapplier import acompanhamento as ac
from jobapplier.desfecho import Desfecho


def test_mais_forte_vence():
    assert ac._mais_forte(["recebida", "entrevista", "resposta"]) is Desfecho.ENTREVISTA
    # Recusa pesa mais que a confirmação automática: é resposta humana.
    assert ac._mais_forte(["recusa", "recebida"]) is Desfecho.RECUSA


def test_mais_forte_ignora_tipo_desconhecido():
    assert ac._mais_forte(["banana", "recebida"]) is Desfecho.RECEBIDA
    assert ac._mais_forte([]) is None


def test_resumo_aguardando_desconta_resposta_e_recusa(monkeypatch):
    monkeypatch.setattr(ac, "por_vaga", lambda ids: {
        1: None, 2: Desfecho.RECEBIDA, 3: Desfecho.RESPOSTA,
        4: Desfecho.ENTREVISTA, 5: Desfecho.OFERTA, 6: Desfecho.RECUSA,
    })

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query(self, *a):
            return self

        def filter(self, *a):
            return self

        def all(self):
            return [(i,) for i in range(1, 7)]

    monkeypatch.setattr("jobapplier.database.connection.get_session", lambda: _S())
    r = ac.resumo()
    assert r.enviadas == 6
    assert r.com_resposta == 3          # resposta, entrevista, oferta
    assert r.entrevistas == 2           # entrevista + oferta
    assert r.ofertas == 1
    assert r.recusas == 1
    assert r.aguardando == 2            # sem nada + só recebida


def test_rotulos_cobrem_todo_desfecho_e_o_vazio():
    for d in Desfecho:
        assert d in ac.ROTULOS, d
    assert None in ac.ROTULOS
