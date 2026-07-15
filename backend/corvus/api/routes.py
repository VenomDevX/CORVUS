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


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "app": "Corvus"}


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
    repo = request.app.state.repo
    return {
        "provider": repo.get_setting("provider"),
        "model": repo.get_setting("model"),
        "tts_voice": repo.get_setting("tts_voice"),
    }


@router.patch("/settings")
def patch_settings(request: Request, body: SettingsPatch) -> dict:
    repo = request.app.state.repo
    if body.provider is not None:
        if body.provider != "ollama":
            raise HTTPException(400, "only the ollama provider is available until Milestone 8")
        repo.set_setting("provider", body.provider)
    if body.model is not None:
        repo.set_setting("model", body.model)
    if body.tts_voice is not None:
        repo.set_setting("tts_voice", body.tts_voice)
        if request.app.state.voice is not None:
            request.app.state.voice.speaker.voice = body.tts_voice
    return get_settings(request)


@router.get("/models")
async def list_models(request: Request) -> dict:
    try:
        return {"models": await request.app.state.provider.list_models()}
    except Exception as exc:
        raise HTTPException(502, f"Ollama unreachable: {exc}")


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


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Save a user-attached file so agent actions (e.g. describe_image) can read
    it by path. Returned into the message so the model can act on it."""
    uploads = data_dir() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._- ")
    dest = uploads / f"{datetime.now():%Y%m%d-%H%M%S}-{safe_name}"
    dest.write_bytes(await file.read())
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
