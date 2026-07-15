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
from .routes import router
from .voice import voice_router
from .ws import ws_router


def create_app(
    repo: Repository | None = None,
    provider: OllamaProvider | None = None,
    database: Path | None = None,
    voice: bool | object = True,
    browser: bool | object = True,
) -> FastAPI:
    """voice/browser: True builds the real subsystem, False disables it (tests),
    or pass a pre-built engine object."""
    log = setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if voice is not False:
            if voice is True:
                from ..voice.pipeline import VoicePipeline

                app.state.voice = VoicePipeline(app.state.repo, app.state.provider)
            else:
                app.state.voice = voice
            await app.state.voice.start()
        yield
        if app.state.voice is not None:
            await app.state.voice.stop()
        if app.state.browser is not None:
            await app.state.browser.close()
        app.state.repo.close()

    app = FastAPI(title="Corvus", version=__version__, lifespan=lifespan)

    from ..actions.registry import build_default_registry

    app.state.repo = repo or Repository(database or db_path())
    app.state.provider = provider or OllamaProvider()
    app.state.log = log
    app.state.voice = None

    if browser is False:
        app.state.browser = None
    elif browser is True:
        from ..automation.browser import BrowserEngine

        app.state.browser = BrowserEngine(data_dir() / "downloads")
    else:
        app.state.browser = browser

    app.state.registry = build_default_registry(
        browser=app.state.browser,
        provider=app.state.provider,
        get_model=lambda: app.state.repo.get_setting("model"),
    )
    if app.state.repo.get_setting("model") is None:
        app.state.repo.set_setting("model", DEFAULT_MODEL)
    if app.state.repo.get_setting("provider") is None:
        app.state.repo.set_setting("provider", "ollama")

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

    return app
