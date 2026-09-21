"""A fila do dia: poucas, prontas, e a decisão passa pela porta certa.

O serviço é compartilhado pelo webapp e pelo painel da extensão, então a regra
que ele guarda vale nas duas telas. O que estes testes protegem: o padrão é
curto (412 cartões não são escolha), vaga sem dossiê não é oferecida quando há
outra pronta, e nenhuma decisão vinda de fora grava status que o mapa não
conhece — `enviada_confirmada` por POST furaria a invariante 2.
"""
import pytest

from jobapplier import fila


def _item(id, score, cv=True):
    return fila.ItemFila(id=id, titulo=f"Vaga {id}", empresa="acme",
                         empresa_exibicao="Acme", plataforma="gupy", link="",
                         score=score, localizacao="", modalidade="",
                         status="aprovada", tem_curriculo=cv, tem_carta=cv)


def test_do_dia_e_curta_por_padrao(monkeypatch):
    monkeypatch.setattr(fila, "listar",
                        lambda **k: [_item(i, 90 - i) for i in range(30)])
    assert len(fila.do_dia()) == fila.DO_DIA == 5


def test_do_dia_prefere_quem_ja_tem_dossie(monkeypatch):
    """Oferecer vaga sem currículo pronto é oferecer trabalho, não oportunidade."""
    monkeypatch.setattr(fila, "listar", lambda **k: [
        _item(1, 99, cv=False), _item(2, 95), _item(3, 94, cv=False), _item(4, 90),
    ])
    assert [i.id for i in fila.do_dia(2)] == [2, 4]


def test_do_dia_nao_fica_vazia_se_nada_esta_pronto(monkeypatch):
    """Fila vazia esconderia que há vaga esperando — devolve as melhores mesmo."""
    monkeypatch.setattr(fila, "listar",
                        lambda **k: [_item(1, 99, cv=False), _item(2, 95, cv=False)])
    assert [i.id for i in fila.do_dia(1)] == [1]


def test_decisao_desconhecida_e_recusada_antes_do_banco():
    """Nem chega a abrir sessão: `ValueError` sai da checagem do mapa."""
    with pytest.raises(ValueError):
        fila.decidir(1, "enviada_confirmada")


def test_mapa_de_decisoes_nunca_grava_status_de_prova():
    """'enviada' pela extensão vira `enviada_manual`, nunca um status que
    `guard.ja_candidatado` trate como confirmado sem prova."""
    assert fila.DECISOES["enviada"] == "enviada_manual"
    assert "enviada_confirmada" not in fila.DECISOES.values()
    assert "candidatada" not in fila.DECISOES.values()


def test_item_serializa_tudo_que_o_painel_le():
    d = _item(7, 88).como_dict()
    for chave in ("id", "titulo", "empresa_exibicao", "plataforma", "link",
                  "score", "localizacao", "modalidade", "tem_curriculo", "tem_carta"):
        assert chave in d
