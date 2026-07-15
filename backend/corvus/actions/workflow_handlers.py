"""Workflow actions (Milestone 8): create, run, list, delete workflows.

The agent builds workflows from natural language ("make a morning routine that
opens Chrome and Spotify"), so these actions are how a workflow gets defined
and triggered by voice or chat.
"""

from ..workflows.engine import WorkflowEngine, WorkflowError
from .registry import ActionResult, ActionSpec, Registry, Risk


def register_workflow_actions(reg: Registry, engine: WorkflowEngine) -> None:
    async def create_workflow(name: str, steps: list, trigger: str = "manual",
                              at: str | None = None, phrase: str | None = None) -> ActionResult:
        config = {}
        if trigger == "schedule" and at:
            config["at"] = at
        if trigger == "voice" and phrase:
            config["phrase"] = phrase
        try:
            wf = engine.create(name, steps, trigger, config)
        except WorkflowError as exc:
            return ActionResult(False, str(exc))
        return ActionResult(True, f"Saved workflow “{name}” with {len(wf['steps'])} step(s).",
                            {"workflow": wf})

    reg.register(ActionSpec(
        "create_workflow",
        "Create or update a saved workflow: an ordered list of steps, each an action name with "
        "arguments. trigger is 'manual', 'schedule' (with at='HH:MM'), or 'voice' (with a phrase). "
        "High-risk actions aren't allowed in workflows.",
        {"type": "object", "properties": {
            "name": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "action": {"type": "string"},
                "arguments": {"type": "object"},
            }, "required": ["action"]}},
            "trigger": {"type": "string", "enum": ["manual", "schedule", "voice"]},
            "at": {"type": "string", "description": "HH:MM for a scheduled workflow"},
            "phrase": {"type": "string", "description": "Spoken phrase for a voice workflow"},
        }, "required": ["name", "steps"]},
        Risk.LOW, create_workflow, category="workflows",
    ))

    async def run_workflow(name: str) -> ActionResult:
        try:
            results = await engine.run(name)
        except WorkflowError as exc:
            return ActionResult(False, str(exc))
        ok = sum(1 for r in results if r.ok)
        summary = "; ".join(f"{r.action}: {'ok' if r.ok else 'failed'}" for r in results)
        return ActionResult(ok == len(results), f"Ran “{name}” — {ok}/{len(results)} steps ok. {summary}")

    reg.register(ActionSpec(
        "run_workflow", "Run a saved workflow by name.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        Risk.LOW, run_workflow, category="workflows",
    ))

    async def list_workflows() -> ActionResult:
        workflows = engine.list()
        names = ", ".join(w["name"] for w in workflows) or "none"
        return ActionResult(True, f"Saved workflows: {names}.", {"workflows": workflows})

    reg.register(ActionSpec(
        "list_workflows", "List saved workflows.",
        {"type": "object", "properties": {}}, Risk.SAFE, list_workflows, category="workflows",
    ))

    async def delete_workflow(name: str) -> ActionResult:
        ok = engine.delete(name)
        return ActionResult(ok, f"Deleted workflow “{name}”." if ok else f"No workflow named “{name}”.")

    reg.register(ActionSpec(
        "delete_workflow", "Delete a saved workflow by name.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        Risk.LOW, delete_workflow, category="workflows",
    ))
