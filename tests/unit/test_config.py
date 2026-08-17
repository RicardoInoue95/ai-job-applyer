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


def test_get_gemini_key_none_when_missing(tmp_config):
    assert tmp_config.get_gemini_key() is None


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
