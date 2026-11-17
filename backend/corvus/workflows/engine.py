"""Workflow engine: ordered sequences of registered actions.

A workflow reuses the Milestone 6 action registry - each step is an action name
plus arguments. Workflows are for routines (open my apps, read my schedule), so
high-risk actions are barred from them; those must stay in interactive chat
where the confirmation card is shown. Workflows trigger manually, at a time of
day (optionally on given weekdays), every N minutes, when Corvus starts, after
N idle minutes, when a new file lands in a folder, or by a spoken phrase.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from ..actions.registry import Risk

log = structlog.get_logger("corvus")

# Risk tiers allowed inside a saved workflow. Workflows run with no
# confirmation card, so anything that normally confirms (medium/high) is barred.
ALLOWED_RISK = {Risk.SAFE, Risk.LOW}
# Workflow-management actions can't be steps (no recursion, no self-editing).
BARRED_ACTIONS = {"create_workflow", "run_workflow", "delete_workflow"}
# Must match the CHECK constraint in memory/db.py.
TRIGGERS = ("manual", "schedule", "interval", "startup", "idle", "folder", "voice")
# In-progress downloads and temp files: the finished file arrives under its real name.
_PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".tmp", ".download")


class WorkflowError(Exception):
    pass


def idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input in this Windows session."""
    if sys.platform != "win32":
        return 0.0
    import ctypes

    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LastInputInfo(ctypes.sizeof(LastInputInfo))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    tick = ctypes.windll.kernel32.GetTickCount
    tick.restype = ctypes.c_uint
    # Both are 32-bit millisecond tick counts; mask so the 49-day wrap still subtracts.
    return ((tick() - info.dwTime) & 0xFFFFFFFF) / 1000


def _minutes(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440:
        raise WorkflowError(f"{label} must be a whole number of minutes from 1 to 1440.")
    return value


def validate_trigger(kind: str, config: dict | None) -> dict:
    """Check a trigger's settings and return only the keys it uses."""
    config = config or {}
    if kind not in TRIGGERS:
        raise WorkflowError(f"Unknown trigger '{kind}'. Use one of: {', '.join(TRIGGERS)}.")
    if kind == "schedule":
        try:  # normalize "8:00" -> "08:00" so string comparison orders correctly
            at = datetime.strptime(str(config.get("at", "")), "%H:%M").strftime("%H:%M")
        except ValueError:
            raise WorkflowError("A scheduled workflow needs a time as HH:MM, e.g. 08:30.") from None
        days = config.get("days")
        if days is None:
            return {"at": at}
        if (not isinstance(days, list) or not days
                or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in days)):
            raise WorkflowError("days must be a list of weekdays, 0 (Monday) to 6 (Sunday).")
        return {"at": at, "days": sorted(set(days))}
    if kind == "interval":
        return {"every_minutes": _minutes(config.get("every_minutes"), "every_minutes")}
    if kind == "idle":
        return {"minutes": _minutes(config.get("minutes"), "Idle minutes")}
    if kind == "folder":
        raw = str(config.get("path") or "").strip()
        path = Path(raw).expanduser() if raw else None
        if not path or not path.is_absolute() or not path.is_dir():
            raise WorkflowError("A folder workflow needs the full path of an existing folder.")
        return {"path": str(path.resolve())}
    if kind == "voice":
        phrase = str(config.get("phrase") or "").strip()
        if not re.search(r"\w", phrase):
            raise WorkflowError("A voice workflow needs a phrase to listen for.")
        return {"phrase": phrase}
    return {}  # manual, startup


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
        self._running: set[str] = set()
        # Per-trigger memory between ticks (in memory: a restart re-baselines,
        # so nothing fires just because Corvus was closed for a while).
        self._last_interval: dict[str, datetime] = {}
        self._idle_fired: set[str] = set()
        self._folder_seen: dict[tuple[str, str], set[str]] = {}

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
        config = validate_trigger(trigger_type, trigger_config)
        row = self.repo.create_workflow(name, clean, trigger_type, config)
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

    async def start(self, run_startup: bool = True) -> None:
        """Start the trigger loop. run_startup=False after a crash restart, so a
        respawned backend doesn't re-run the launch routine."""
        self._loop = asyncio.get_running_loop()
        if run_startup:
            for row in self.repo.list_workflows():
                if row["trigger_type"] == "startup" and row["enabled"]:
                    self._spawn(row["name"])
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
        """Check every timed/watching trigger once a minute (minute resolution)."""
        # ponytail: one 60s tick for all triggers; folder/idle react within a
        # minute. Add a faster watcher (ReadDirectoryChangesW) if that's too slow.
        fired: set[tuple[str, object]] = set()
        first = True
        while True:
            now = datetime.now()
            for row in self.repo.list_workflows():
                if not row["enabled"]:
                    continue
                try:
                    due = self._due(row["name"], row["trigger_type"],
                                    json.loads(row["trigger_config"]), now, first, fired)
                except Exception as exc:  # noqa: BLE001 - one bad row must never stop the loop
                    log.warning("workflow_trigger_check_failed", workflow=row["name"], error=str(exc))
                    continue
                if due:
                    self._spawn(row["name"])
            first = False
            fired = {k for k in fired if k[1] == now.date()}
            # Align to the next minute boundary.
            await asyncio.sleep(60 - datetime.now().second)

    def _due(self, name: str, kind: str, config: dict, now: datetime,
             first: bool, fired: set) -> bool:
        """Whether a workflow's trigger fires on this tick. Updates trigger memory."""
        if kind == "schedule":
            # Keyed by (name, date) so a skipped minute (sleep, slow tick) still
            # fires late the same day, and a new day always resets. Times already
            # past at startup are marked done: no surprise catch-up runs on launch.
            try:
                at = datetime.strptime(str(config.get("at", "")), "%H:%M").strftime("%H:%M")
            except ValueError:
                return False
            days = config.get("days")
            key = (name, now.date())
            if (days and now.weekday() not in days) or at > now.strftime("%H:%M") or key in fired:
                return False
            fired.add(key)
            return not first or at == now.strftime("%H:%M")
        if kind == "interval":
            last = self._last_interval.get(name)
            if last is not None and now - last < timedelta(minutes=config["every_minutes"]):
                return False
            self._last_interval[name] = now
            return last is not None  # the first tick only starts the clock
        if kind == "idle":
            # Once per idle stretch: re-arms when input resumes.
            if idle_seconds() < config["minutes"] * 60:
                self._idle_fired.discard(name)
                return False
            if name in self._idle_fired:
                return False
            self._idle_fired.add(name)
            return True
        if kind == "folder":
            key = (name, config["path"])
            try:
                names = {e.name for e in Path(config["path"]).iterdir()
                         if e.is_file() and not e.name.lower().endswith(_PARTIAL_SUFFIXES)}
            except OSError:
                return False  # folder gone or unreadable: wait for it to come back
            seen = self._folder_seen.get(key)
            self._folder_seen[key] = names
            # The first look is the baseline; only files added after it count.
            return seen is not None and bool(names - seen)
        return False

    def _spawn(self, name: str) -> None:
        """Run a workflow without blocking the scheduler tick."""
        if name in self._running:
            log.info("workflow_already_running", workflow=name)
            return

        async def go() -> None:
            try:
                await self.run(name)
            except Exception as exc:
                log.warning("workflow_scheduled_run_failed", workflow=name, error=str(exc))
            finally:
                self._running.discard(name)

        self._running.add(name)
        task = asyncio.get_running_loop().create_task(go())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
