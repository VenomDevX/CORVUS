"""Corvus Plugin SDK.

A plugin is a folder containing:

  manifest.json   metadata + declared permissions + the actions it adds
  plugin.py       defines `register(ctx: PluginContext)`

`register` adds actions with `ctx.action(...)`. A plugin only loads if the user
has enabled it and granted every permission its manifest declares; the context
exposes just the capabilities that were granted. Plugins run in-process, so the
permission grant is a trust decision - the UI shows exactly what each one asks
for before it's enabled.

Manifest schema (manifest.json):
{
  "id": "text-tools",              // unique, kebab-case
  "name": "Text Tools",
  "version": "1.0.0",
  "description": "Word count and text transforms.",
  "author": "Corvus",
  "permissions": ["network"],      // subset of Permission values; may be []
  "entry": "plugin.py"             // optional, defaults to plugin.py
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ..actions.registry import ActionResult, ActionSpec, Registry, Risk


class Permission(str, Enum):
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    AUTOMATION = "automation"
    CLIPBOARD = "clipboard"
    SYSTEM = "system"


ALL_PERMISSIONS = [p.value for p in Permission]


class PluginError(Exception):
    pass


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    author: str
    permissions: list[str] = field(default_factory=list)
    entry: str = "plugin.py"
    path: Path | None = None

    @staticmethod
    def load(directory: Path) -> "PluginManifest":
        manifest_file = directory / "manifest.json"
        if not manifest_file.exists():
            raise PluginError(f"no manifest.json in {directory}")
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        for required in ("id", "name", "version", "description", "author"):
            if required not in data:
                raise PluginError(f"manifest missing '{required}' in {directory}")
        perms = data.get("permissions", [])
        for p in perms:
            if p not in ALL_PERMISSIONS:
                raise PluginError(f"unknown permission '{p}' in {data['id']}")
        return PluginManifest(
            id=data["id"], name=data["name"], version=data["version"],
            description=data["description"], author=data["author"],
            permissions=perms, entry=data.get("entry", "plugin.py"), path=directory,
        )


class PluginContext:
    """Handed to a plugin's register(); its surface reflects granted permissions."""

    def __init__(self, manifest: PluginManifest, registry: Registry, granted: set[str]):
        self._manifest = manifest
        self._registry = registry
        self._granted = granted
        self.registered_actions: list[str] = []

    def has_permission(self, permission: str) -> bool:
        return permission in self._granted

    def require(self, permission: str) -> None:
        if permission not in self._granted:
            raise PluginError(f"plugin '{self._manifest.id}' lacks the '{permission}' permission")

    def action(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
        risk: Risk = Risk.SAFE,
        confirm_prompt: Callable[[dict], str] | None = None,
    ) -> None:
        """Register a plugin action. Names are namespaced by plugin id."""
        full_name = f"{self._manifest.id}.{name}"
        self._registry.register(ActionSpec(
            full_name, description, parameters, risk, handler,
            confirm_prompt=confirm_prompt, category=f"plugin:{self._manifest.id}",
        ))
        self.registered_actions.append(full_name)


# Re-exported so plugin.py can build results without importing internals.
__all__ = ["Permission", "PluginContext", "PluginManifest", "PluginError", "ActionResult", "Risk"]
