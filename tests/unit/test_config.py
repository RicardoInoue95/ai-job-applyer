import json
import tempfile
from pathlib import Path

import pytest

from config.manager import ConfigManager


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
