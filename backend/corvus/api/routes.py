"""REST routes: health, conversations, memories, settings, models, logs."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import __version__
from ..log import tail_log

router = APIRouter()


class ConversationCreate(BaseModel):
    title: str


class SettingsPatch(BaseModel):
    provider: str | None = None
    model: str | None = None


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
    return {"provider": repo.get_setting("provider"), "model": repo.get_setting("model")}


@router.patch("/settings")
def patch_settings(request: Request, body: SettingsPatch) -> dict:
    repo = request.app.state.repo
    if body.provider is not None:
        if body.provider != "ollama":
            raise HTTPException(400, "only the ollama provider is available until Milestone 8")
        repo.set_setting("provider", body.provider)
    if body.model is not None:
        repo.set_setting("model", body.model)
    return {"provider": repo.get_setting("provider"), "model": repo.get_setting("model")}


@router.get("/models")
async def list_models(request: Request) -> dict:
    try:
        return {"models": await request.app.state.provider.list_models()}
    except Exception as exc:
        raise HTTPException(502, f"Ollama unreachable: {exc}")


@router.get("/logs")
def logs(limit: int = 200) -> list[dict]:
    return tail_log(min(limit, 1000))
