
import pytest

from jobapplier.config.manager import ConfigManager


@pytest.fixture
def tmp_config(tmp_path):
    return ConfigManager(path=tmp_path / "config.json")


def test_load_returns_empty_when_no_file(tmp_config):
    assert tmp_config.load() == {}


def test_save_and_load_roundtrip(tmp_config):
    data = {"gemini": {"api_key": "test-key"}, "coleta": {"cargos_alvo": ["Data Engineer"]}}
    tmp_config.save(data)
    assert tmp_config.load() == data


def test_get_nested_key(tmp_config):
    tmp_config.save({"gemini": {"api_key": "abc123"}})
    assert tmp_config.get("gemini", "api_key") == "abc123"


def test_get_missing_key_returns_default(tmp_config):
    assert tmp_config.get("nonexistent", default="fallback") == "fallback"


def test_set_nested_key(tmp_config):
    tmp_config.set("gemini", "api_key", value="new-key")
    assert tmp_config.get("gemini", "api_key") == "new-key"


def test_set_preserves_other_keys(tmp_config):
    tmp_config.save({"existing": "value"})
    tmp_config.set("gemini", "api_key", value="key")
    assert tmp_config.get("existing") == "value"


def test_is_setup_complete_false_when_no_config(tmp_config):
    assert not tmp_config.is_setup_complete()


def test_is_setup_complete_true_when_configured(tmp_config):
    tmp_config.save({"setup_completed": True})
    assert tmp_config.is_setup_complete()


def test_get_gemini_key_none_when_missing(tmp_config, monkeypatch):
    # get_gemini_key agora consulta o ambiente antes do JSON, então o teste
    # precisa garantir que a variável não está definida.
    monkeypatch.delenv("AIJOB_GEMINI_API_KEY", raising=False)
    assert tmp_config.get_gemini_key() is None


def test_get_gemini_key_prefers_env_over_json(tmp_config, monkeypatch):
    tmp_config.save({"gemini": {"api_key": "do-json"}})
    monkeypatch.setenv("AIJOB_GEMINI_API_KEY", "do-ambiente")
    assert tmp_config.get_gemini_key() == "do-ambiente"


def test_get_gemini_key_fallback_usa_config_da_instancia(tmp_config, monkeypatch):
    # Regressão: get_gemini_key delegava para um ConfigManager novo e ignorava
    # o path da instância, fazendo ConfigManager(path=X) ler outro arquivo.
    monkeypatch.delenv("AIJOB_GEMINI_API_KEY", raising=False)
    tmp_config.save({"gemini": {"api_key": "chave-desta-instancia"}})
    assert tmp_config.get_gemini_key() == "chave-desta-instancia"


def test_get_target_companies_empty_by_default(tmp_config):
    companies = tmp_config.get_target_companies()
    assert companies == {"greenhouse": [], "lever": []}


def test_get_target_companies_returns_saved(tmp_config):
    tmp_config.save({
        "coleta": {
            "empresas_greenhouse": ["airbnb", "discord"],
            "empresas_lever": ["shopify"],
        }
    })
    companies = tmp_config.get_target_companies()
    assert companies["greenhouse"] == ["airbnb", "discord"]
    assert companies["lever"] == ["shopify"]


# ── Estado do envio: a UI não pode mostrar valor velho ────────────────────────
# Investiguei um "bug" em que o Dashboard dizia modo sombra e a tela Revisar
# dizia envio ativo no mesmo instante. Não era bug: o estado mudou ENTRE as duas
# capturas. Mas responder isso custou subir o app e dirigir um navegador, e a
# propriedade que torna a resposta óbvia cabe num teste de um segundo.

def test_load_reflete_mudanca_no_arquivo(tmp_path):
    """`ConfigManager.load()` relê o disco. Se algum dia ganhar cache, cada
    página da UI passa a mostrar o estado do momento em que foi construída — e
    o pior caso é a tela onde você LIGA o envio mentir sobre ele estar ligado."""
    import json

    from jobapplier.config.manager import ConfigManager

    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"risco": {"modo_sombra": True}}), encoding="utf-8")
    cfg = ConfigManager(path=caminho)
    assert cfg.load()["risco"]["modo_sombra"] is True

    caminho.write_text(json.dumps({"risco": {"modo_sombra": False}}), encoding="utf-8")
    assert cfg.load()["risco"]["modo_sombra"] is False, "load() está com cache"


def test_esta_ativo_acompanha_o_arquivo(tmp_path):
    """Contrato que app.py e o Dashboard compartilham: os dois chamam
    `esta_ativo(config)`, então basta esta função ser honesta."""
    import json

    from jobapplier import envio_automatico as ea
    from jobapplier.config.manager import ConfigManager

    caminho = tmp_path / "config.json"
    cfg = ConfigManager(path=caminho)

    caminho.write_text(json.dumps({"risco": {"modo_sombra": True}}), encoding="utf-8")
    assert ea.esta_ativo(cfg) is False
    caminho.write_text(json.dumps({"risco": {"modo_sombra": False}}), encoding="utf-8")
    assert ea.esta_ativo(cfg) is True


def test_sem_config_o_padrao_e_modo_sombra(tmp_path):
    """Arquivo ausente ou corrompido não pode significar "pode enviar"."""
    from jobapplier import envio_automatico as ea
    from jobapplier.config.manager import ConfigManager

    ausente = ConfigManager(path=tmp_path / "nao_existe.json")
    assert ea.esta_ativo(ausente) is False

    corrompido = tmp_path / "quebrado.json"
    corrompido.write_text("{ isto nao e json", encoding="utf-8")
    assert ea.esta_ativo(ConfigManager(path=corrompido)) is False
