"""Tests for bonfires.sdk.config."""

import pytest

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import ConfigError


def test_config_from_explicit_params():
    cfg = BonfiresConfig(
        api_key="key",
        bonfire_id="bf-1",
        agent_id="ag-1",
        vault_dir="/tmp/vault",
    )
    assert cfg.api_key == "key"
    assert cfg.bonfire_id == "bf-1"
    assert cfg.agent_id == "ag-1"
    assert cfg.group_id == "bf-1:ag-1"
    assert cfg.api_url == "https://tnt-v2.api.bonfires.ai"


def test_config_missing_api_key():
    with pytest.raises(ConfigError, match="api_key"):
        BonfiresConfig(api_key="", bonfire_id="bf-1", agent_id="ag-1", vault_dir="/tmp")


def test_config_missing_bonfire_id():
    with pytest.raises(ConfigError, match="bonfire_id"):
        BonfiresConfig(api_key="key", bonfire_id="", agent_id="ag-1", vault_dir="/tmp")


def test_config_missing_vault_dir():
    with pytest.raises(ConfigError, match="vault_dir"):
        BonfiresConfig(api_key="key", bonfire_id="bf-1", agent_id="ag-1", vault_dir="")


def test_config_custom_group_id():
    cfg = BonfiresConfig(
        api_key="key",
        bonfire_id="bf-1",
        agent_id="ag-1",
        vault_dir="/tmp/vault",
        group_id="custom-group",
    )
    assert cfg.group_id == "custom-group"


def test_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BONFIRE_API_KEY", "env-key")
    monkeypatch.setenv("BONFIRE_ID", "env-bf")
    monkeypatch.setenv("BONFIRE_AGENT_ID", "env-ag")
    monkeypatch.setenv("BONFIRE_VAULT_DIR", str(tmp_path))
    # Clear any config file influence
    monkeypatch.chdir(tmp_path)

    cfg = BonfiresConfig.from_env()
    assert cfg.api_key == "env-key"
    assert cfg.bonfire_id == "env-bf"
    assert cfg.agent_id == "env-ag"
    assert cfg.vault_dir == str(tmp_path)


def test_config_from_env_missing_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("BONFIRE_API_KEY", raising=False)
    monkeypatch.delenv("BONFIRE_ID", raising=False)
    monkeypatch.delenv("BONFIRE_AGENT_ID", raising=False)
    monkeypatch.delenv("BONFIRE_VAULT_DIR", raising=False)
    monkeypatch.delenv("BONFIRE_API_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    # Prevent reading the real global config file
    monkeypatch.setattr("bonfires.sdk.config.CONFIG_FILE", tmp_path / "nonexistent.env")

    with pytest.raises(ConfigError, match="Missing config"):
        BonfiresConfig.from_env()
