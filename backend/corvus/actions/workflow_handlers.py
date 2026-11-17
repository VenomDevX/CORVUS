"""Workflow actions (Milestone 8): create, run, list, delete workflows.

The agent builds workflows from natural language ("make a morning routine that
opens Chrome and Spotify"), so these actions are how a workflow gets defined
and triggered by voice or chat.
"""

from ..workflows.engine import TRIGGERS, WorkflowEngine, WorkflowError
from .registry import ActionResult, ActionSpec, Registry, Risk

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _trigger_config(args: dict) -> dict:
    """Map the flat action arguments onto the engine's per-trigger config."""
    trigger = args.get("trigger") or "manual"
    if trigger == "schedule":
        return {k: args[k] for k in ("at", "days") if args.get(k) is not None}
    return {"interval": {"every_minutes": args.get("every_minutes")},
            "idle": {"minutes": args.get("idle_minutes")},
            "folder": {"path": args.get("folder")},
            "voice": {"phrase": args.get("phrase")}}.get(trigger, {})


def _describe_create(args: dict) -> str:
    steps = args.get("steps") or []
    names = ", ".join(str(s.get("action")) for s in steps if isinstance(s, dict)) or "no steps"
    trigger = args.get("trigger") or "manual"
    days = args.get("days")
    on_days = (" on " + ", ".join(_DAY_NAMES[d] for d in days if isinstance(d, int) and 0 <= d <= 6)
               if days else " every day")
    when = {
        "schedule": f"{on_days} at {args.get('at')}",
        "interval": f" every {args.get('every_minutes')} minutes",
        "startup": " every time Corvus starts",
        "idle": f" after {args.get('idle_minutes')} minutes with no keyboard or mouse input",
        # Anything that can write to the folder (a download, a sync client) can set this off.
        "folder": f" whenever a new file appears in {args.get('folder')}",
        "voice": f" when you say “{args.get('phrase')}”",
    }.get(trigger, " when you run it")
    unattended = "" if trigger in ("manual", "voice") else " It will run on its own, without asking."
    return f"Save workflow “{args.get('name')}” that runs {names}{when}?{unattended}"


def register_workflow_actions(reg: Registry, engine: WorkflowEngine) -> None:
    async def create_workflow(name: str, steps: list, trigger: str = "manual", **trigger_args) -> ActionResult:
        try:
            wf = engine.create(name, steps, trigger, _trigger_config({"trigger": trigger, **trigger_args}))
        except WorkflowError as exc:
            return ActionResult(False, str(exc))
        return ActionResult(True, f"Saved workflow “{name}” with {len(wf['steps'])} step(s).",
                            {"workflow": wf})

    reg.register(ActionSpec(
        "create_workflow",
        "Create or update a saved workflow: an ordered list of steps, each an action name with "
        "arguments. trigger: 'manual'; 'schedule' (at='HH:MM', optional days); 'interval' "
        "(every_minutes); 'startup' (when Corvus starts); 'idle' (idle_minutes without input); "
        "'folder' (folder = full path; runs when a new file appears there); 'voice' (phrase). "
        "Only safe and low-risk actions are allowed in workflows.",
        {"type": "object", "properties": {
            "name": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "action": {"type": "string"},
                "arguments": {"type": "object"},
            }, "required": ["action"]}},
            "trigger": {"type": "string", "enum": list(TRIGGERS)},
            "at": {"type": "string", "pattern": r"^\d{1,2}:\d{2}$",
                   "description": "HH:MM (24h) for a scheduled workflow"},
            "days": {"type": "array", "minItems": 1, "uniqueItems": True,
                     "items": {"type": "integer", "minimum": 0, "maximum": 6},
                     "description": "Weekdays for a schedule, 0=Monday..6=Sunday; omit for every day"},
            "every_minutes": {"type": "integer", "minimum": 1, "maximum": 1440,
                              "description": "Minutes between runs for an interval workflow"},
            "idle_minutes": {"type": "integer", "minimum": 1, "maximum": 1440,
                             "description": "Minutes without input before an idle workflow runs"},
            "folder": {"type": "string", "description": "Full folder path for a folder workflow"},
            "phrase": {"type": "string", "description": "Spoken phrase for a voice workflow"},
        }, "required": ["name", "steps"], "additionalProperties": False},
        Risk.MEDIUM, create_workflow, category="workflows",
        confirm_prompt=lambda a: _describe_create(a),
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
        Risk.MEDIUM, delete_workflow, category="workflows",
        confirm_prompt=lambda a: f"Delete the saved workflow “{a.get('name')}”?",
    ))
