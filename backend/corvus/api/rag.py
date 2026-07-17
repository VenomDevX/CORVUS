"""Documents index (local RAG) endpoints."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

rag_router = APIRouter()


class IndexBody(BaseModel):
    path: str


class SearchBody(BaseModel):
    query: str


def _index(request: Request):
    idx = getattr(request.app.state, "rag", None)
    if idx is None:
        raise HTTPException(503, "documents index unavailable")
    return idx


@rag_router.get("/rag/status")
def rag_status(request: Request) -> dict:
    idx = _index(request)
    folder = request.app.state.repo.get_setting("rag_folder") or ""
    return {"folder": folder, **idx.status()}


@rag_router.post("/rag/index")
async def rag_index(request: Request, body: IndexBody) -> dict:
    idx = _index(request)
    folder = Path(body.path).expanduser()
    if not folder.is_dir():
        raise HTTPException(400, "folder does not exist")
    if idx.indexing:
        raise HTTPException(409, "an index run is already in progress")
    request.app.state.repo.set_setting("rag_folder", str(folder))
    result = await asyncio.to_thread(idx.index_folder, folder)
    return {"ok": True, **result}


@rag_router.post("/rag/search")
def rag_search(request: Request, body: SearchBody) -> list[dict]:
    if not body.query.strip():
        return []
    return _index(request).search(body.query)
