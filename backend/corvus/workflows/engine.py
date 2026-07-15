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
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from ..actions.registry import Risk

log = structlog.get_logger("corvus")

# Risk tiers allowed inside a saved workflow (no destructive/high-impact steps).
ALLOWED_RISK = {Risk.SAFE, Risk.LOW, Risk.MEDIUM}


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

    # -- validation & CRUD ----------------------------------------------------

    def validate_steps(self, steps: list) -> list[dict]:
        if not steps:
            raise WorkflowError("A workflow needs at least one step.")
        clean = []
        for step in steps:
            name = step.get("action")
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
        steps = json.loads(row["steps"])
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
        low = text.lower().strip().rstrip(".!?")
        for row in self.repo.list_workflows():
            if row["trigger_type"] != "voice" or not row["enabled"]:
                continue
            phrase = json.loads(row["trigger_config"]).get("phrase", "").lower().strip()
            if phrase and (phrase in low or low in phrase):
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
        fired_today: set[tuple[str, str]] = set()
        while True:
            now = datetime.now()
            hhmm = now.strftime("%H:%M")
            if hhmm == "00:00":
                fired_today.clear()
            for row in self.repo.list_workflows():
                if row["trigger_type"] != "schedule" or not row["enabled"]:
                    continue
                at = json.loads(row["trigger_config"]).get("at", "")
                key = (row["name"], hhmm)
                if at == hhmm and key not in fired_today:
                    fired_today.add(key)
                    with contextlib.suppress(Exception):
                        await self.run(row["name"])
            # Align to the next minute boundary.
            await asyncio.sleep(60 - datetime.now().second)
