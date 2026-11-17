"""Provider catalog and the active-provider manager.

All providers implement the same LLMProvider protocol. ProviderManager presents
the *currently selected* provider behind that same interface, so the agent loop,
voice pipeline, and memory extractor never need to know which backend is live.
Switching providers or keys just calls reload().
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog

from .. import egress
from .anthropic import AnthropicProvider
from .base import Delta, Message
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider
from .vault import KeyVault

log = structlog.get_logger("corvus")


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    label: str
    needs_key: bool
    default_model: str
    key_url: str = ""


PROVIDERS: dict[str, ProviderInfo] = {
    "ollama": ProviderInfo("ollama", "Ollama (local)", False, "qwen2.5-coder:latest"),
    "openai": ProviderInfo("openai", "OpenAI", True, "gpt-4o", "https://platform.openai.com/api-keys"),
    "anthropic": ProviderInfo("anthropic", "Anthropic (Claude)", True, "claude-sonnet-4-5",
                              "https://console.anthropic.com/settings/keys"),
    "gemini": ProviderInfo("gemini", "Google Gemini", True, "gemini-2.5-flash",
                           "https://aistudio.google.com/app/apikey"),
    "deepseek": ProviderInfo("deepseek", "DeepSeek", True, "deepseek-chat",
                             "https://platform.deepseek.com/api_keys"),
}


def build_provider(name: str, vault: KeyVault):
    """Construct a provider instance from its name and stored key."""
    if name == "ollama":
        return OllamaProvider()
    key = vault.get_key(name) or ""
    if name == "openai":
        return OpenAICompatProvider("openai", "https://api.openai.com/v1", key)
    if name == "deepseek":
        return OpenAICompatProvider("deepseek", "https://api.deepseek.com/v1", key)
    if name == "anthropic":
        return AnthropicProvider(key)
    if name == "gemini":
        return GeminiProvider(key)
    raise ValueError(f"unknown provider: {name}")


def cloud_label(provider) -> str | None:
    """Display name of the active provider when it is off-machine, else None."""
    name = getattr(provider, "current_name", None)
    if not name or name == "ollama" or name not in PROVIDERS:
        return None
    return PROVIDERS[name].label


def model_setting_key(provider: str) -> str:
    return f"model:{provider}"


class ProviderManager:
    """The active provider, resolved from settings, behind the LLMProvider API."""

    name = "corvus-active"

    def __init__(self, repo, vault: KeyVault):
        self.repo = repo
        self.vault = vault
        self._delegate = None
        self.reload()

    def reload(self) -> None:
        import os
        import sys

        name = self.repo.get_setting("provider") or "ollama"
        if name not in PROVIDERS:
            name = "ollama"
        if os.environ.get("CORVUS_TEST_PROVIDER") == "scripted" and not getattr(sys, "frozen", False):
            from .scripted import ScriptedProvider

            self._delegate = ScriptedProvider()  # e2e tests only, never in a packaged build
            log.warning("provider_scripted_for_tests")
            return
        self._delegate = build_provider(name, self.vault)
        log.info("provider_active", provider=name)

    @property
    def current_name(self) -> str:
        return self.repo.get_setting("provider") or "ollama"

    def current_model(self) -> str:
        name = self.current_name
        return self.repo.get_setting(model_setting_key(name)) or PROVIDERS[name].default_model

    # -- delegated LLMProvider surface ---------------------------------------
    # Every call to a cloud provider is recorded in the session egress log
    # (size + kinds of content, never the text) for the Privacy view.

    def _record(self, kind: str, messages, model: str) -> None:
        label = cloud_label(self)
        if label:
            egress.record_messages(label, kind, messages, model)

    def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        self._record("chat", messages, model)
        return self._delegate.stream_chat(messages, model)

    def stream_chat_with_tools(self, messages, model, tools) -> AsyncIterator[Delta]:
        self._record("chat", messages, model)
        return self._delegate.stream_chat_with_tools(messages, model, tools)

    async def complete(self, messages: list[Message], model: str) -> str:
        self._record("background (memory)", messages, model)
        return await self._delegate.complete(messages, model)

    async def list_models(self) -> list[str]:
        return await self._delegate.list_models()

    async def describe_image(self, image_path: str, model: str) -> str:
        if hasattr(self._delegate, "describe_image"):
            label = cloud_label(self)
            if label:
                import os

                egress.record(label, "image", os.path.getsize(image_path), ["image"], model)
            return await self._delegate.describe_image(image_path, model)
        raise RuntimeError("the active provider can't describe images")
