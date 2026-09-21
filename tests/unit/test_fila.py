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


def test_abrir_registra_sem_tirar_da_fila():
    """"Abrir e candidatar" grava que o link foi aberto — não que a candidatura
    saiu. A vaga continua na fila até "enviei" ou "não é para mim"."""
    assert fila.DECISOES["abrir"] == "aberta"
    assert "aberta" in fila.NA_FILA


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


def test_precisam_de_voce_e_o_corte_de_confianca(monkeypatch):
    """Só as excelentes com dossiê. 275 na barra é a lista maçante de volta;
    o corte é o mesmo em que o sistema confiaria para enviar sozinho."""
    monkeypatch.setattr(fila, "corte_de_atencao", lambda: 85)
    visto = {}

    def _listar(**k):
        visto.update(k)
        return [_item(1, 90), _item(2, 88, cv=False),
                fila.ItemFila(id=3, titulo="", empresa="", empresa_exibicao="",
                              plataforma="gupy", link="", score=95, localizacao="",
                              modalidade="", status="pendente", tem_curriculo=True)]

    monkeypatch.setattr(fila, "listar", _listar)
    assert [i.id for i in fila.precisam_de_voce()] == [1]
    assert visto["score_min"] == 85


@pytest.mark.parametrize("bruto, limpo", [
    ("12393045 - Engenheiro de Dados Pleno", "Engenheiro de Dados Pleno"),
    ("12473727 | Analista de Dados PL", "Analista de Dados PL"),
    ("0731 - Analista de Dados - Ciclo", "Analista de Dados - Ciclo"),
    ("3 Analistas de Dados", "3 Analistas de Dados"),
    ("Analista de BI", "Analista de BI"),
    ("", ""),
])
def test_titulo_exibicao_tira_o_codigo_do_ats(bruto, limpo):
    assert fila.titulo_exibicao(bruto) == limpo
