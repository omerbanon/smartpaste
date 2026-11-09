"""API key storage: Keychain first, config.json never (after migration)."""

import json

import pytest

from smartpaste import config, keychain


@pytest.fixture
def env(tmp_path, monkeypatch):
    store: dict[str, str] = {}
    state = {"writable": True}

    def set_secret(value):
        if not state["writable"]:
            return False
        store["key"] = value
        return True

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(keychain, "get_secret", lambda: store.get("key"))
    monkeypatch.setattr(keychain, "set_secret", set_secret)
    monkeypatch.setattr(keychain, "delete_secret", lambda: store.pop("key", None))
    return store, state, tmp_path / "config.json"


def test_save_moves_key_to_keychain(env):
    store, _, path = env
    config.save_config({"api_key": " sk-1 ", "model": "m"})
    assert store["key"] == "sk-1"
    assert "api_key" not in json.loads(path.read_text())
    assert config.get_api_key() == "sk-1"
    assert config.is_configured()
    assert "api_key" not in config.load_config()


def test_empty_key_deletes_it(env):
    store, _, _ = env
    store["key"] = "sk-old"
    config.save_config({"api_key": ""})
    assert "key" not in store
    assert not config.is_configured()


def test_migrates_plain_text_key(env):
    store, _, path = env
    path.write_text(json.dumps({"api_key": "sk-legacy", "model": "m"}))
    assert config.get_api_key() == "sk-legacy"  # works before migration too
    config.migrate_api_key_to_keychain()
    assert store["key"] == "sk-legacy"
    assert json.loads(path.read_text()) == {"model": "m"}


def test_keychain_failure_keeps_key_usable(env):
    _, state, path = env
    state["writable"] = False
    config.save_config({"api_key": "sk-2"})
    assert json.loads(path.read_text())["api_key"] == "sk-2"
    config.migrate_api_key_to_keychain()
    assert config.get_api_key() == "sk-2"
