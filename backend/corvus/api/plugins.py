"""Plugin marketplace + permission endpoints (Extensions / Plugins UI)."""

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ..plugins.manager import MAX_ZIP_BYTES
from ..plugins.sdk import PluginError

plugin_router = APIRouter()


class PermissionsBody(BaseModel):
    permissions: list[str]


def _manager(request: Request):
    mgr = request.app.state.plugins
    if mgr is None:
        raise HTTPException(503, "plugins unavailable")
    return mgr


@plugin_router.get("/plugins")
def list_plugins(request: Request) -> list[dict]:
    mgr = request.app.state.plugins
    return mgr.catalog() if mgr is not None else []


@plugin_router.post("/plugins/install")
async def install_plugin(request: Request, file: UploadFile) -> dict:
    """Install a plugin from an uploaded .zip; it lands disabled so the user
    still reviews permissions + code hash before enabling (consent moment)."""
    mgr = _manager(request)
    # Read at most one byte past the cap so an oversized upload is rejected
    # without buffering the whole thing in memory.
    data = await file.read(MAX_ZIP_BYTES + 1)
    try:
        manifest = mgr.install_zip(data)
    except PluginError as exc:
        raise HTTPException(400, str(exc)) from exc
    entry = next((p for p in mgr.catalog() if p["id"] == manifest.id), None)
    if entry is None:
        raise HTTPException(500, "plugin installed but not discovered")
    return entry


@plugin_router.delete("/plugins/{pid}")
def uninstall_plugin(request: Request, pid: str) -> dict:
    if not _manager(request).uninstall(pid):
        raise HTTPException(404, "plugin not found or is built-in")
    return {"ok": True}


@plugin_router.post("/plugins/{pid}/enable")
def enable_plugin(request: Request, pid: str) -> dict:
    mgr = _manager(request)
    if pid not in mgr.manifests:
        mgr.discover()
    if pid not in mgr.manifests:
        raise HTTPException(404, "plugin not found")
    return mgr.enable(pid)


@plugin_router.post("/plugins/{pid}/disable")
def disable_plugin(request: Request, pid: str) -> dict:
    _manager(request).disable(pid)
    return {"ok": True}


@plugin_router.put("/plugins/{pid}/permissions")
def set_permissions(request: Request, pid: str, body: PermissionsBody) -> dict:
    mgr = _manager(request)
    mgr.discover()
    manifest = mgr.manifests.get(pid)
    if manifest is None:
        raise HTTPException(404, "plugin not found")
    invalid = set(body.permissions) - set(manifest.permissions)
    if invalid:
        raise HTTPException(400, f"plugin doesn't declare: {', '.join(invalid)}")
    mgr.set_permissions(pid, body.permissions)
    return {"ok": True, "granted": mgr.granted_permissions(pid)}
