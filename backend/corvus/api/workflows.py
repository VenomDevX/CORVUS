"""Workflow REST endpoints for the Tasks/Workflows UI."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..workflows.engine import WorkflowError

workflow_router = APIRouter()


class WorkflowBody(BaseModel):
    name: str
    steps: list[dict]
    trigger_type: str = "manual"
    trigger_config: dict = {}


def _engine(request: Request):
    engine = request.app.state.workflows
    if engine is None:
        raise HTTPException(503, "workflows unavailable")
    return engine


@workflow_router.get("/workflows")
def list_workflows(request: Request) -> list[dict]:
    engine = request.app.state.workflows
    return engine.list() if engine is not None else []


@workflow_router.post("/workflows")
def create_workflow(request: Request, body: WorkflowBody) -> dict:
    try:
        return _engine(request).create(body.name, body.steps, body.trigger_type, body.trigger_config)
    except WorkflowError as exc:
        raise HTTPException(400, str(exc))


@workflow_router.post("/workflows/{name}/run")
async def run_workflow(request: Request, name: str) -> dict:
    try:
        results = await _engine(request).run(name)
    except WorkflowError as exc:
        raise HTTPException(404, str(exc))
    return {"results": [{"action": r.action, "ok": r.ok, "message": r.message} for r in results]}


@workflow_router.delete("/workflows/{name}")
def delete_workflow(request: Request, name: str) -> dict:
    if not _engine(request).delete(name):
        raise HTTPException(404, "workflow not found")
    return {"ok": True}
