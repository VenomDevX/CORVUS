"""Corvus FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import DEFAULT_MODEL, data_dir, db_path
from ..llm.ollama import OllamaProvider
from ..log import setup_logging
from ..memory.repository import Repository
from .notifications import notify_router
from .plugins import plugin_router
from .routes import router
from .voice import voice_router
from .workflows import workflow_router
from .ws import ws_router


def create_app(
    repo: Repository | None = None,
    provider: OllamaProvider | None = None,
    database: Path | None = None,
    voice: bool | object = True,
    browser: bool | object = True,
    notifications: bool = True,
) -> FastAPI:
    """voice/browser: True builds the real subsystem, False disables it (tests),
    or pass a pre-built engine object. notifications: enable the reminder hub."""
    log = setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.notifications is not None:
            await app.state.notifications.start()
        await app.state.workflows.start()
        if voice is not False:
            if voice is True:
                from ..voice.pipeline import VoicePipeline

                app.state.voice = VoicePipeline(
                    app.state.repo, app.state.provider, workflows=app.state.workflows
                )
            else:
                app.state.voice = voice
            await app.state.voice.start()
        yield
        if app.state.voice is not None:
            await app.state.voice.stop()
        await app.state.workflows.stop()
        if app.state.browser is not None:
            await app.state.browser.close()
        if app.state.notifications is not None:
            await app.state.notifications.stop()
        app.state.repo.close()

    app = FastAPI(title="Corvus", version=__version__, lifespan=lifespan)

    from ..actions.registry import build_default_registry

    from ..llm.factory import ProviderManager
    from ..llm.vault import KeyVault

    app.state.repo = repo or Repository(database or db_path())
    app.state.vault = KeyVault(app.state.repo)
    # A caller may inject a provider (tests); otherwise use the active-provider
    # manager so the selected backend (Ollama/OpenAI/Anthropic/…) is live.
    app.state.provider = provider or ProviderManager(app.state.repo, app.state.vault)
    app.state.log = log
    app.state.voice = None

    if browser is False:
        app.state.browser = None
    elif browser is True:
        from ..automation.browser import BrowserEngine

        app.state.browser = BrowserEngine(data_dir() / "downloads")
    else:
        app.state.browser = browser

    if notifications:
        from ..notifications.hub import NotificationHub

        app.state.notifications = NotificationHub(app.state.repo)
    else:
        app.state.notifications = None

    def active_model() -> str:
        prov = app.state.provider
        if hasattr(prov, "current_model"):
            return prov.current_model()
        return app.state.repo.get_setting("model") or DEFAULT_MODEL

    app.state.active_model = active_model
    app.state.registry = build_default_registry(
        browser=app.state.browser,
        provider=app.state.provider,
        get_model=active_model,
        notifications=app.state.notifications,
    )

    # Workflows reuse the assembled registry; their actions register back into it.
    from ..workflows.engine import WorkflowEngine
    from ..actions.workflow_handlers import register_workflow_actions

    app.state.workflows = WorkflowEngine(app.state.repo, app.state.registry, app.state.notifications)
    register_workflow_actions(app.state.registry, app.state.workflows)

    # Plugins load their actions into the same registry (enabled + granted only).
    from ..plugins.manager import PluginManager

    app.state.plugins = PluginManager(app.state.repo, app.state.registry)
    app.state.plugins.load_enabled()
    if app.state.repo.get_setting("provider") is None:
        app.state.repo.set_setting("provider", "ollama")
    if app.state.repo.get_setting("model:ollama") is None:
        app.state.repo.set_setting("model:ollama", DEFAULT_MODEL)

    # The server binds to loopback only; the Electron renderer's origin varies
    # (vite dev server / file://), so allow any origin on this local socket.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(voice_router)
    app.include_router(notify_router)
    app.include_router(workflow_router)
    app.include_router(plugin_router)

    return app
