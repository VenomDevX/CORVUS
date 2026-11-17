"""Data controls: privacy/egress view, retention, export/import, wipe."""

from __future__ import annotations

import shutil

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from .. import egress
from ..backup import BackupError, export_bundle, import_bundle
from ..config import data_dir
from ..retention import retention_days, set_retention_days

data_router = APIRouter()
log = structlog.get_logger("corvus")

MAX_BACKUP_BYTES = 200 * 1024 * 1024
# Downloaded runtimes and models, not user data: a wipe keeps them so the
# user doesn't re-download gigabytes.
KEEP_ON_WIPE = frozenset({"playwright-browsers", "image-models", "piper-voices"})


class ExportBody(BaseModel):
    passphrase: str


class RetentionBody(BaseModel):
    screenshots: int | None = None
    uploads: int | None = None
    downloads: int | None = None


@data_router.get("/egress")
def egress_log(request: Request) -> dict:
    from ..llm.factory import cloud_label

    return {"cloud_provider": cloud_label(request.app.state.provider), "entries": egress.entries()}


@data_router.get("/data/retention")
def get_retention(request: Request) -> dict:
    return retention_days(request.app.state.repo)


@data_router.patch("/data/retention")
def patch_retention(request: Request, body: RetentionBody) -> dict:
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        set_retention_days(request.app.state.repo, values)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return retention_days(request.app.state.repo)


@data_router.post("/data/export")
def export_data(request: Request, body: ExportBody) -> Response:
    try:
        bundle = export_bundle(request.app.state.repo, body.passphrase)
    except BackupError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(
        bundle,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="corvus-backup.corvusbak"'},
    )


@data_router.post("/data/import")
async def import_data(request: Request, file: UploadFile = File(...), passphrase: str = Form(...)) -> dict:
    data = await file.read(MAX_BACKUP_BYTES + 1)
    if len(data) > MAX_BACKUP_BYTES:
        raise HTTPException(413, "backup file is too large")
    try:
        return import_bundle(request.app.state.repo, request.app.state.workflows, data, passphrase,
                             hub=request.app.state.notifications)
    except BackupError as exc:
        raise HTTPException(400, str(exc)) from exc


def wipe_data_dir() -> list[str]:
    """Delete everything in the data dir except downloaded runtimes/models.
    Runs in the backend process: under Store Python the data dir is
    virtualized, so only this process sees the real files."""
    import logging

    # Release the log file handle so logs/ can be deleted on Windows.
    for handler in list(logging.getLogger("corvus").handlers):
        handler.close()
    failed = []
    for child in data_dir().iterdir():
        if child.name in KEEP_ON_WIPE:
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError:
            failed.append(child.name)
    return failed


@data_router.post("/data/wipe")
def wipe(request: Request) -> dict:
    """Delete all user data (admin token: main process shows a native dialog
    first). Shutdown closes every database; the lifespan then deletes the
    files and the Electron supervisor starts a fresh backend."""
    server = getattr(request.app.state, "server", None)
    if server is None:
        raise HTTPException(503, "wipe is only available when run via corvus.main")
    rag = request.app.state.rag
    chroma = getattr(rag, "_chroma", None)
    if chroma is not None:
        # Chroma keeps its files open; drop the collection while it's live.
        try:
            chroma.client.delete_collection("documents")
        except Exception:  # noqa: BLE001 - rmtree below still removes what it can
            pass
    log.warning("data_wipe_requested")
    request.app.state.wipe_on_exit = True
    server.should_exit = True
    return {"ok": True}
