"""O interruptor do envio automático: ligar é deliberado, desligar é fácil.

O modo sombra só era editável em `data/config.json`. Virou botão, e estes testes
protegem as decisões do desenho: ativar não reenfileira nada sozinho, e o
reenfileiramento entra pela porta oficial da esteira ('aprovada'), onde os
limites do guard continuam valendo.
"""
import inspect

from jobapplier import envio_automatico as ea


class _ConfigFake:
    def __init__(self, dados=None):
        self.dados = dados or {}
        self.salvos = []

    def load(self):
        return self.dados

    def save(self, cfg):
        self.dados = cfg
        self.salvos.append(cfg)


# ── Liga/desliga ──────────────────────────────────────────────────────────────

def test_por_padrao_esta_desligado():
    """Sem config nenhuma, o sombra vale — nunca 'ligado por omissão'."""
    assert ea.esta_ativo(_ConfigFake({})) is False
    assert ea.esta_ativo(_ConfigFake({"risco": {}})) is False


def test_ativar_escreve_a_mesma_chave_que_o_orquestrador_le():
    """Botão e esteira têm que olhar o MESMO lugar. Um caminho paralelo aqui
    faria o Dashboard dizer 'ligado' com a esteira ainda em sombra."""
    cfg = _ConfigFake({})
    ea.ativar(cfg)

    assert cfg.dados["risco"]["modo_sombra"] is False
    assert cfg.salvos, "tem que persistir, não só mutar em memória"
    assert ea.esta_ativo(cfg) is True


def test_desativar_religa_o_sombra():
    cfg = _ConfigFake({"risco": {"modo_sombra": False}})
    ea.desativar(cfg)
    assert cfg.dados["risco"]["modo_sombra"] is True
    assert ea.esta_ativo(cfg) is False


def test_ativar_nao_toca_no_banco():
    """Ativar libera vagas FUTURAS. Reenfileirar as já preparadas é outro botão
    — decisão do usuário: o mesmo clique nunca liga o sistema E dispara envios."""
    fonte = inspect.getsource(ea.ativar)
    assert "get_session" not in fonte
    assert "Vaga" not in fonte


def test_threshold_auto_vem_da_config_com_default_conservador():
    assert ea.threshold_auto(_ConfigFake({})) == 85
    assert ea.threshold_auto(_ConfigFake({"scoring": {"threshold_auto": 90}})) == 90


# ── Reenfileiramento ──────────────────────────────────────────────────────────

def test_reenfileirar_entra_pela_porta_oficial():
    """Devolve a 'aprovada' — o único status que a esteira processa (invariante
    1). Enviar direto daqui contornaria guard, limites e disjuntor."""
    fonte = inspect.getsource(ea.reenfileirar)
    assert '"aprovada"' in fonte
    assert '"pronta_para_revisao"' in fonte
    assert "apply" not in fonte and "submit" not in fonte, \
        "reenfileirar muda status; nunca envia"


def test_quem_qualifica_vem_do_registro_de_plataformas():
    """Nada de hardcode 'greenhouse': quando o Lever ganhar applicator, o botão
    passa a valer para ele sem ninguém lembrar de editar aqui."""
    for funcao in (ea.qualificaveis, ea.reenfileirar):
        fonte = inspect.getsource(funcao)
        assert "com_automacao()" in fonte
        assert '"greenhouse"' not in fonte


def test_sem_plataforma_automatizavel_nao_ha_o_que_reenfileirar(monkeypatch):
    from jobapplier import plataformas

    monkeypatch.setattr(plataformas, "com_automacao", lambda: [])
    assert ea.qualificaveis(_ConfigFake({})) == []
    assert ea.reenfileirar(_ConfigFake({})) == 0


def test_o_dashboard_usa_este_modulo_e_nao_reimplementa():
    """Regra de negócio não vive em pages/: a página só chama botões daqui."""
    from pathlib import Path

    pagina = (Path(__file__).resolve().parents[2] / "ui" / "pages"
              / "2_Dashboard.py").read_text(encoding="utf-8")
    assert "envio_automatico" in pagina
    assert 'update({"status"' not in pagina, \
        "reenfileirar na página seria regra de negócio em pages/"
