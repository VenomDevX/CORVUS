"""DPAPI key-vault tests (Windows-encrypted, real crypt32)."""

from corvus.llm.factory import PROVIDERS, ProviderManager, build_provider
from corvus.llm.vault import KeyVault


def test_encrypts_roundtrips_and_clears(repo):
    vault = KeyVault(repo)
    assert vault.get_key("openai") is None

    vault.set_key("openai", "sk-secret-9")
    assert vault.get_key("openai") == "sk-secret-9"
    assert vault.has_key("openai")

    # Stored value is ciphertext, not the key.
    raw = repo.get_setting("apikey:openai")
    assert "sk-secret-9" not in raw

    vault.clear_key("openai")
    assert vault.get_key("openai") is None
    assert not vault.has_key("openai")


def test_empty_key_clears(repo):
    vault = KeyVault(repo)
    vault.set_key("gemini", "x")
    vault.set_key("gemini", "")
    assert not vault.has_key("gemini")


def test_provider_catalog_complete():
    for name in ("ollama", "openai", "anthropic", "gemini", "deepseek"):
        assert name in PROVIDERS
    assert PROVIDERS["ollama"].needs_key is False
    assert PROVIDERS["anthropic"].needs_key is True


def test_build_provider_selects_type(repo):
    vault = KeyVault(repo)
    vault.set_key("openai", "k")
    assert build_provider("ollama", vault).name == "ollama"
    assert build_provider("openai", vault).name == "openai"
    assert build_provider("deepseek", vault).name == "deepseek"
    assert build_provider("anthropic", vault).name == "anthropic"
    assert build_provider("gemini", vault).name == "gemini"


def test_manager_reflects_selected_provider_and_model(repo):
    vault = KeyVault(repo)
    mgr = ProviderManager(repo, vault)
    assert mgr.current_name == "ollama"
    assert mgr.current_model() == PROVIDERS["ollama"].default_model

    repo.set_setting("provider", "anthropic")
    repo.set_setting("model:anthropic", "claude-opus-4-1")
    mgr.reload()
    assert mgr.current_name == "anthropic"
    assert mgr.current_model() == "claude-opus-4-1"
