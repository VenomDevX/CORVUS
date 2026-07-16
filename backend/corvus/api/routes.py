"""REST routes: health, conversations, memories, settings, models, logs."""

from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from .. import __version__
from ..config import data_dir
from ..log import tail_log

router = APIRouter()


class ConversationCreate(BaseModel):
    title: str


class SettingsPatch(BaseModel):
    provider: str | None = None
    model: str | None = None
    tts_voice: str | None = None
    onboarding_complete: bool | None = None


class ApiKeyBody(BaseModel):
    provider: str
    key: str


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "app": "Corvus"}


@router.get("/session")
def session_state(request: Request) -> dict:
    """Crash-recovery state: whether the last run ended cleanly and which
    conversation to restore."""
    return request.app.state.session.state()


@router.get("/conversations")
def list_conversations(request: Request) -> list[dict]:
    return request.app.state.repo.list_conversations()


@router.post("/conversations")
def create_conversation(request: Request, body: ConversationCreate) -> dict:
    return request.app.state.repo.create_conversation(body.title)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(request: Request, conversation_id: int) -> dict:
    if not request.app.state.repo.delete_conversation(conversation_id):
        raise HTTPException(404, "conversation not found")
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(request: Request, conversation_id: int) -> list[dict]:
    if request.app.state.repo.get_conversation(conversation_id) is None:
        raise HTTPException(404, "conversation not found")
    return request.app.state.repo.list_messages(conversation_id)


@router.get("/memories")
def list_memories(request: Request) -> list[dict]:
    return request.app.state.repo.list_memories()


@router.delete("/memories/{memory_id}")
def delete_memory(request: Request, memory_id: int) -> dict:
    if not request.app.state.repo.delete_memory(memory_id):
        raise HTTPException(404, "memory not found")
    return {"ok": True}


@router.get("/memories/export")
def export_memories(request: Request) -> Response:
    import json

    payload = json.dumps(
        {"app": "Corvus", "version": __version__, "memories": request.app.state.repo.list_memories()},
        indent=2,
    )
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="corvus-memories.json"'},
    )


@router.get("/settings")
def get_settings(request: Request) -> dict:
    from ..llm.factory import PROVIDERS, model_setting_key

    repo = request.app.state.repo
    provider = repo.get_setting("provider") or "ollama"
    model = repo.get_setting(model_setting_key(provider)) or (
        PROVIDERS[provider].default_model if provider in PROVIDERS else None
    )
    return {
        "provider": provider,
        "model": model,
        "tts_voice": repo.get_setting("tts_voice"),
        "onboarding_complete": repo.get_setting("onboarding_complete") == "true",
    }


@router.patch("/settings")
def patch_settings(request: Request, body: SettingsPatch) -> dict:
    from ..llm.factory import PROVIDERS, model_setting_key

    repo = request.app.state.repo
    reload_provider = False
    if body.provider is not None:
        if body.provider not in PROVIDERS:
            raise HTTPException(400, f"unknown provider: {body.provider}")
        repo.set_setting("provider", body.provider)
        reload_provider = True
    if body.model is not None:
        provider = repo.get_setting("provider") or "ollama"
        repo.set_setting(model_setting_key(provider), body.model)
    if body.tts_voice is not None:
        repo.set_setting("tts_voice", body.tts_voice)
        if request.app.state.voice is not None:
            request.app.state.voice.speaker.voice = body.tts_voice
    if body.onboarding_complete is not None:
        repo.set_setting("onboarding_complete", "true" if body.onboarding_complete else "false")
    if reload_provider and hasattr(request.app.state.provider, "reload"):
        request.app.state.provider.reload()
    return get_settings(request)


@router.get("/system/specs")
async def system_specs() -> dict:
    """Device specs + local-model fit recommendations (first-run setup)."""
    from ..system_info import specs

    return await specs()


@router.get("/providers")
def list_providers(request: Request) -> list[dict]:
    """Catalog of LLM providers with which have a key configured."""
    from ..llm.factory import PROVIDERS

    vault = request.app.state.vault
    return [
        {
            "name": info.name,
            "label": info.label,
            "needs_key": info.needs_key,
            "has_key": vault.has_key(info.name) if info.needs_key else True,
            "default_model": info.default_model,
            "key_url": info.key_url,
        }
        for info in PROVIDERS.values()
    ]


@router.put("/providers/key")
def set_provider_key(request: Request, body: ApiKeyBody) -> dict:
    from ..llm.factory import PROVIDERS

    if body.provider not in PROVIDERS or not PROVIDERS[body.provider].needs_key:
        raise HTTPException(400, f"{body.provider} does not take an API key")
    request.app.state.vault.set_key(body.provider, body.key)
    if request.app.state.repo.get_setting("provider") == body.provider:
        request.app.state.provider.reload()
    return {"ok": True, "has_key": request.app.state.vault.has_key(body.provider)}


@router.delete("/providers/key/{provider}")
def clear_provider_key(request: Request, provider: str) -> dict:
    request.app.state.vault.clear_key(provider)
    return {"ok": True}


@router.get("/models")
async def list_models(request: Request) -> dict:
    try:
        return {"models": await request.app.state.provider.list_models()}
    except Exception as exc:
        raise HTTPException(502, f"provider unreachable: {exc}")


@router.get("/logs")
def logs(limit: int = 200) -> list[dict]:
    return tail_log(min(limit, 1000))


@router.get("/actions")
def list_actions(request: Request) -> list[dict]:
    """The registered action catalog (for the Tasks view)."""
    registry = request.app.state.registry
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "risk": spec.risk.value,
            "category": spec.category,
            "requires_confirmation": spec.requires_confirmation,
        }
        for spec in registry.all()
    ]


@router.get("/actions/log")
def action_log(request: Request, limit: int = 100) -> list[dict]:
    return request.app.state.repo.list_actions(min(limit, 500))


# Upload hardening (SECURITY.md item 9): streamed to disk in chunks with a
# hard size cap, filename reduced to a safe character set (no path separators,
# so no traversal out of the uploads dir).
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Save a user-attached file so agent actions (e.g. describe_image) can read
    it by path. Returned into the message so the model can act on it."""
    uploads = data_dir() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    raw_name = (file.filename or "file").replace("..", "")
    safe_name = "".join(c for c in raw_name if c.isalnum() or c in "._- ")
    if safe_name.startswith("."):
        safe_name = "file" + safe_name
    dest = uploads / f"{datetime.now():%Y%m%d-%H%M%S}-{safe_name or 'file'}"

    bytes_read = 0
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if bytes_read > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File exceeds the 50MB upload limit")
                f.write(chunk)
    except HTTPException:
        # Unlink only after the handle is closed — Windows can't delete open files.
        dest.unlink(missing_ok=True)
        raise

    return {"path": str(dest), "filename": safe_name}


@router.get("/downloads")
def downloads(request: Request) -> list[dict]:
    """Files Corvus has downloaded via browser automation (Milestone 7)."""
    browser = request.app.state.browser
    return browser.download_list() if browser is not None else []


@router.get("/browser/status")
def browser_status(request: Request) -> dict:
    browser = request.app.state.browser
    if browser is None:
        return {"available": False, "open": False}
    return {
        "available": True,
        "open": browser.is_open,
        "consented_sites": sorted(browser.consented_sites),
        "downloads": len(browser.downloads),
    }
