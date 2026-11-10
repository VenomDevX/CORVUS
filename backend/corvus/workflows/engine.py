"""Workflow engine: ordered sequences of registered actions.

A workflow reuses the Milestone 6 action registry - each step is an action name
plus arguments. Workflows are for routines (open my apps, read my schedule), so
high-risk actions are barred from them; those must stay in interactive chat
where the confirmation card is shown. Workflows trigger manually, on a daily
schedule, or by a spoken phrase.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from ..actions.registry import Risk

log = structlog.get_logger("corvus")

# Risk tiers allowed inside a saved workflow. Workflows run with no
# confirmation card, so anything that normally confirms (medium/high) is barred.
ALLOWED_RISK = {Risk.SAFE, Risk.LOW}
# Workflow-management actions can't be steps (no recursion, no self-editing).
BARRED_ACTIONS = {"create_workflow", "run_workflow", "delete_workflow"}


class WorkflowError(Exception):
    pass


@dataclass
class StepResult:
    action: str
    ok: bool
    message: str


class WorkflowEngine:
    def __init__(self, repo, registry, hub=None):
        self.repo = repo
        self.registry = registry
        self.hub = hub
        self._loop: asyncio.AbstractEventLoop | None = None
        self._scheduler: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()

    # -- validation & CRUD ----------------------------------------------------

    def validate_steps(self, steps: list) -> list[dict]:
        if not steps:
            raise WorkflowError("A workflow needs at least one step.")
        clean = []
        for step in steps:
            if not isinstance(step, dict):
                raise WorkflowError("Each workflow step must be an object with an action.")
            name = step.get("action")
            if name in BARRED_ACTIONS:
                raise WorkflowError(f"'{name}' can't be used as a workflow step.")
            spec = self.registry.get(name)
            if spec is None:
                raise WorkflowError(f"Unknown action in workflow: {name}")
            if spec.risk not in ALLOWED_RISK:
                raise WorkflowError(
                    f"'{name}' is {spec.risk.value}-risk and can't run unattended in a workflow; "
                    "ask for it directly in chat instead."
                )
            clean.append({"action": name, "arguments": step.get("arguments", {})})
        return clean

    def create(self, name: str, steps: list, trigger_type: str = "manual",
               trigger_config: dict | None = None) -> dict:
        clean = self.validate_steps(steps)
        row = self.repo.create_workflow(name, clean, trigger_type, trigger_config)
        self._reschedule()
        return self._decode(row)

    def list(self) -> list[dict]:
        return [self._decode(r) for r in self.repo.list_workflows()]

    def delete(self, name: str) -> bool:
        ok = self.repo.delete_workflow(name)
        self._reschedule()
        return ok

    @staticmethod
    def _decode(row: dict) -> dict:
        return {
            **row,
            "steps": json.loads(row["steps"]),
            "trigger_config": json.loads(row["trigger_config"]),
            "enabled": bool(row["enabled"]),
        }

    # -- execution ------------------------------------------------------------

    async def run(self, name: str) -> list[StepResult]:
        row = self.repo.get_workflow(name)
        if row is None:
            raise WorkflowError(f"No workflow named '{name}'.")
        # Re-check at run time: an action's risk may have changed since the
        # workflow was saved (e.g. a plugin re-registered it), or the row predates the rules.
        steps = self.validate_steps(json.loads(row["steps"]))
        log.info("workflow_run", workflow=name, steps=len(steps))
        if self.hub:
            self.hub.notify("Corvus", f"Running workflow “{name}”…")

        results: list[StepResult] = []
        for step in steps:
            result = await self.registry.execute(step["action"], step.get("arguments", {}))
            results.append(StepResult(step["action"], result.ok, result.message))
            if not result.ok:
                log.warning("workflow_step_failed", workflow=name, action=step["action"])
        ok = sum(1 for r in results if r.ok)
        if self.hub:
            self.hub.notify("Corvus", f"Workflow “{name}” done: {ok}/{len(results)} steps ok.")
        return results

    # -- voice trigger --------------------------------------------------------

    def match_voice(self, text: str) -> str | None:
        """Return the name of a voice-triggered workflow matching the phrase."""
        # Whole-phrase, word-boundary match only: Whisper hallucinates short
        # words ("you", ".") on near-silence, which must never fire a workflow.
        low = " ".join(re.findall(r"\w+", text.lower()))
        if not low:
            return None
        for row in self.repo.list_workflows():
            if row["trigger_type"] != "voice" or not row["enabled"]:
                continue
            phrase = " ".join(re.findall(r"\w+", json.loads(row["trigger_config"]).get("phrase", "").lower()))
            if phrase and re.search(rf"\b{re.escape(phrase)}\b", low):
                return row["name"]
        return None

    # -- scheduler ------------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._scheduler = self._loop.create_task(self._schedule_loop())
        log.info("workflow_engine_started")

    async def stop(self) -> None:
        if self._scheduler:
            self._scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler

    def _reschedule(self) -> None:
        # The schedule loop re-reads workflows each minute, so nothing to do
        # beyond letting it pick up the change on its next tick.
        pass

    async def _schedule_loop(self) -> None:
        """Fire 'schedule' workflows at their daily HH:MM (minute resolution)."""
        # Keyed by (name, date) so a skipped minute (sleep, slow tick) still
        # fires late the same day, and a new day always resets. Times already
        # past at startup are marked done: no surprise catch-up runs on launch.
        fired: set[tuple[str, object]] = set()
        first = True
        while True:
            now = datetime.now()
            hhmm, today = now.strftime("%H:%M"), now.date()
            for row in self.repo.list_workflows():
                if row["trigger_type"] != "schedule" or not row["enabled"]:
                    continue
                try:  # normalize "8:00" -> "08:00" so string comparison orders correctly
                    at = datetime.strptime(
                        str(json.loads(row["trigger_config"]).get("at", "")), "%H:%M"
                    ).strftime("%H:%M")
                except ValueError:
                    continue
                key = (row["name"], today)
                if not at or at > hhmm or key in fired:
                    continue
                fired.add(key)
                if not first or at == hhmm:
                    self._spawn(row["name"])
            first = False
            fired = {k for k in fired if k[1] == today}
            # Align to the next minute boundary.
            await asyncio.sleep(60 - datetime.now().second)

    def _spawn(self, name: str) -> None:
        """Run a workflow without blocking the scheduler tick."""
        async def go() -> None:
            try:
                await self.run(name)
            except Exception as exc:
                log.warning("workflow_scheduled_run_failed", workflow=name, error=str(exc))

        task = asyncio.get_running_loop().create_task(go())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
