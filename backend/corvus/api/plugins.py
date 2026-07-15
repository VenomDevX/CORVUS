"""Plugin marketplace + permission endpoints (Extensions / Plugins UI)."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
