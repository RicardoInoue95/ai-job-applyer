"""Pretensão é a única resposta que é âncora, não fato — e erra caro dos dois lados.

Alto demais filtra por orçamento antes de qualquer conversa. Baixo demais fixa o
teto da negociação e ainda sinaliza que o candidato se vê abaixo do nível da vaga.
"""
import pytest

from jobapplier import paths
from jobapplier import salario as s

FAIXA = s.Faixa(minimo=7000, alvo=9000, maximo=10000, fator_pj=1.30)
CONFIG = {"pretensao": {"minimo": 7000, "alvo": 9000, "maximo": 10000, "fator_pj": 1.30}}

#: Os testes do caminho de produção leem a pretensão real em data/config.json,
#: que só existe na máquina do candidato. Fora dela (CI, clone limpo) eles pulam.
requer_config_real = pytest.mark.pessoal


# ── Faixa ─────────────────────────────────────────────────────────────────────

def test_faixa_incoerente_e_recusada_na_construcao():
    """Faixa invertida na config viraria pretensão absurda num formulário real."""
    with pytest.raises(ValueError):
        s.Faixa(minimo=10000, alvo=9000, maximo=7000)
    with pytest.raises(ValueError):
        s.Faixa(minimo=0, alvo=0, maximo=0)


def test_alvo_ausente_vira_o_meio_da_faixa():
    f = s.carregar_faixa({"pretensao": {"minimo": 7000, "maximo": 11000}})
    assert f.alvo == 9000


def test_sem_configuracao_nao_responde():
    """None é 'não responda', não 'responda zero'. Chutar a pretensão de alguém é
    precisão falsa — e um zero num formulário é pior que um campo vazio."""
    assert s.carregar_faixa({}) is None
    assert s.carregar_faixa({"pretensao": {}}) is None
    assert s.carregar_faixa({"pretensao": {"minimo": 7000}}) is None
    assert s.responder(config={}) is None


def test_valor_nao_numerico_na_config_nao_derruba():
    assert s.carregar_faixa({"pretensao": {"minimo": "abc", "maximo": "xyz"}}) is None


# ── Regime ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("Contratação PJ, sem benefícios", "pj"),
    ("Regime: pessoa jurídica", "pj"),
    ("Você precisa ter CNPJ ativo", "pj"),
    ("Contratação CLT com benefícios", "clt"),
    ("Carteira assinada, VR e plano de saúde", "clt"),
    ("Vaga para Analista de Dados em São Paulo", "desconhecido"),
    ("", "desconhecido"),
])
def test_deteccao_de_regime(texto, esperado):
    assert s.detectar_regime(texto) == esperado


def test_clt_ganha_quando_o_anuncio_oferece_os_dois():
    """'CLT ou PJ' quase sempre tem a faixa cotada em CLT. Assumir PJ inflaria a
    pretensão em 30% contra um orçamento que não é esse."""
    assert s.detectar_regime("Contratação CLT ou PJ, a combinar") == "clt"


# ── Valor por senioridade ─────────────────────────────────────────────────────

def test_vaga_senior_pede_o_topo():
    assert s.valor_para(FAIXA, "Senior") == 10000
    assert s.valor_para(FAIXA, "Especialista") == 10000
    assert s.valor_para(FAIXA, "Gerente") == 10000


def test_vaga_pleno_pede_o_alvo():
    assert s.valor_para(FAIXA, "Pleno") == 9000


def test_campo_de_valor_unico_nunca_desce_do_alvo():
    """O número declarado vira o TETO da negociação, nunca o piso: recrutador
    negocia para baixo a partir dele. Pedir o mínimo garante receber o mínimo."""
    assert s.valor_para(FAIXA, "Junior", unico=True) == 9000
    assert s.valor_para(FAIXA, "", unico=True) == 9000
    # Sem essa trava, o mínimo da faixa vazaria para o formulário.
    assert s.valor_para(FAIXA, "Junior", unico=False) == 7000


def test_nunca_ultrapassa_a_faixa_do_usuario():
    """A faixa é decisão dele. O módulo escolhe onde dentro dela, não além."""
    for nivel in ("Junior", "Pleno", "Senior", "Especialista", "Gerente", ""):
        v = s.valor_para(FAIXA, nivel, regime="clt")
        assert FAIXA.minimo <= v <= FAIXA.maximo


# ── Conversão PJ ──────────────────────────────────────────────────────────────

def test_pj_converte_para_manter_o_liquido():
    """R$ 10k CLT ≈ R$ 13k PJ: não há 13º, férias, FGTS nem INSS patronal.
    Declarar valor CLT numa vaga PJ é pedir 30% menos sem perceber."""
    assert s.valor_para(FAIXA, "Senior", regime="pj") == 13000


def test_clt_e_desconhecido_nao_convertem():
    assert s.valor_para(FAIXA, "Senior", regime="clt") == 10000
    assert s.valor_para(FAIXA, "Senior", regime="desconhecido") == 10000


def test_conversao_pj_aparece_na_justificativa():
    """Número diferente do esperado tem que ter causa registrada — quase sempre
    é a conversão."""
    r = s.responder("Contratação PJ", "Senior", config=CONFIG)
    assert r["numero"] == 13000
    assert "PJ" in r["justificativa"]
    assert "13.000" in r["valor"]


# ── Formatação ────────────────────────────────────────────────────────────────

def test_campo_numerico_recebe_so_digitos():
    """ATS valida o campo com regex de número e rejeita 'R$ 9.000' em silêncio:
    o formulário não envia e a causa não aparece em lugar nenhum."""
    assert s.formatar(9000, "number") == "9000"
    assert s.formatar(13000, "numeric") == "13000"


def test_campo_de_texto_recebe_intervalo_quando_ha_espaco():
    assert s.formatar(9000, "input_text", FAIXA) == "R$ 9.000 a R$ 10.000"


def test_no_topo_da_faixa_nao_inventa_intervalo():
    assert s.formatar(10000, "input_text", FAIXA) == "R$ 10.000"


def test_pj_e_declarado_no_texto():
    """Deixar explícito evita a conversa começar com um mal-entendido de 30%."""
    assert "(PJ)" in s.formatar(13000, "input_text", FAIXA, regime="pj")


# ── Ponta a ponta ─────────────────────────────────────────────────────────────

def test_resposta_completa_para_vaga_clt_pleno():
    r = s.responder("Vaga CLT para Analista Pleno de Dados", "Pleno", config=CONFIG)
    assert r["numero"] == 9000
    assert r["regime"] == "clt"
    assert r["valor"] == "R$ 9.000 a R$ 10.000"


def test_a_faixa_configurada_do_usuario_e_respeitada():
    """7 a 10 mil, informado por ele. Nenhum caminho deste módulo sai disso —
    exceto a conversão de regime, que é aritmética, não aumento de pretensão."""
    f = s.carregar_faixa(CONFIG)
    assert (f.minimo, f.maximo) == (7000, 10000)
    assert s.valor_para(f, "Gerente", regime="clt") == 10000


# ── O caminho de produção ─────────────────────────────────────────────────────
# Todo teste acima passa `config` explícito, e por isso o ramo sem argumento
# — o único que produção usa — nunca rodava. Ele chamava `manager.load()`, que
# não existe: `load` é método de `ConfigManager`. `responder()` levantava
# AttributeError em toda vaga com campo de pretensão.

@requer_config_real
def test_carregar_faixa_sem_argumento_le_a_config_real():
    f = s.carregar_faixa()
    assert f is not None, "data/config.json precisa ter 'pretensao'"
    assert f.minimo > 0 and f.maximo >= f.alvo >= f.minimo


@requer_config_real
def test_responder_sem_argumento_nao_levanta():
    """O applicator chama assim, sem passar config."""
    r = s.responder(texto_vaga="Vaga CLT para engenheiro de dados",
                    senioridade="pleno")
    assert r is not None
    assert r["numero"] >= s.carregar_faixa().minimo
    assert r["valor"], "o campo do formulário recebe o texto, não o número"


@requer_config_real
def test_faixa_da_config_bate_com_o_arquivo():
    """Trava a divergência entre o número no config e o número respondido."""
    import json

    bruto = json.loads(paths.CONFIG_JSON.read_text(encoding="utf-8"))["pretensao"]
    f = s.carregar_faixa()
    assert (f.minimo, f.alvo, f.maximo) == (
        float(bruto["minimo"]), float(bruto["alvo"]), float(bruto["maximo"]))
