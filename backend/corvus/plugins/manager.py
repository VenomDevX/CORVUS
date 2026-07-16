"""Plugin discovery, enable/disable, permission grants, and loading.

Plugins are discovered from the bundled samples folder and the user plugins
folder (%LOCALAPPDATA%\\Corvus\\plugins). Enable state and granted permissions
persist in settings. An enabled plugin loads only when every declared
permission is granted; its `register(ctx)` adds namespaced actions to the shared
registry.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import structlog

from ..actions.registry import Registry
from ..config import data_dir
from .sdk import PluginContext, PluginError, PluginManifest

log = structlog.get_logger("corvus")

_BUNDLED = Path(__file__).parent / "samples"


def _enabled_key(pid: str) -> str:
    return f"plugin:{pid}:enabled"


def _perms_key(pid: str) -> str:
    return f"plugin:{pid}:perms"


def _hash_key(pid: str) -> str:
    return f"plugin:{pid}:hash"


class PluginManager:
    def __init__(self, repo, registry: Registry):
        self.repo = repo
        self.registry = registry
        self.manifests: dict[str, PluginManifest] = {}
        self.loaded: dict[str, list[str]] = {}  # plugin id -> action names
        self.errors: dict[str, str] = {}

    def user_dir(self) -> Path:
        d = data_dir() / "plugins"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def discover(self) -> None:
        self.manifests.clear()
        for base in (_BUNDLED, self.user_dir()):
            if not base.exists():
                continue
            for child in base.iterdir():
                if not child.is_dir() or not (child / "manifest.json").exists():
                    continue
                try:
                    manifest = PluginManifest.load(child)
                    self.manifests[manifest.id] = manifest
                except PluginError as exc:
                    log.warning("plugin_manifest_invalid", dir=str(child), error=str(exc))

    # -- state ----------------------------------------------------------------

    def is_enabled(self, pid: str) -> bool:
        return self.repo.get_setting(_enabled_key(pid)) == "true"

    def granted_permissions(self, pid: str) -> set[str]:
        raw = self.repo.get_setting(_perms_key(pid)) or ""
        return {p for p in raw.split(",") if p}

    def code_hash(self, manifest: PluginManifest) -> str | None:
        """SHA-256 of all Python files in the plugin directory."""
        if not manifest.path.exists():
            return None
        hasher = hashlib.sha256()
        # Sort files to ensure deterministic hashing order
        for py_file in sorted(manifest.path.rglob("*.py")):
            hasher.update(py_file.read_bytes())
        return hasher.hexdigest()

    def approved_hash(self, pid: str) -> str | None:
        return self.repo.get_setting(_hash_key(pid))

    def set_permissions(self, pid: str, granted: list[str]) -> None:
        self.repo.set_setting(_perms_key(pid), ",".join(sorted(set(granted))))
        # Reload so the action surface matches the new grants.
        self._unload_one(pid)
        if self.is_enabled(pid) and pid in self.manifests:
            manifest = self.manifests[pid]
            if not set(manifest.permissions) - self.granted_permissions(pid):
                self._load_one(manifest)

    def enable(self, pid: str) -> dict:
        """Enable is the consent moment: it pins the current code hash, so the
        user approves exactly the plugin.py they were shown (SECURITY.md item 4)."""
        self.repo.set_setting(_enabled_key(pid), "true")
        if pid in self.manifests:
            manifest = self.manifests[pid]
            current = self.code_hash(manifest)
            if current:
                self.repo.set_setting(_hash_key(pid), current)
            missing = set(manifest.permissions) - self.granted_permissions(pid)
            if not missing:
                self._load_one(manifest)
        return {"loaded": pid in self.loaded, "error": self.errors.get(pid)}

    def disable(self, pid: str) -> None:
        self.repo.set_setting(_enabled_key(pid), "false")
        self._unload_one(pid)

    def _unload_one(self, pid: str) -> None:
        for action_name in self.loaded.pop(pid, []):
            self.registry.unregister(action_name)
        log.info("plugin_unloaded", plugin=pid)

    # -- loading --------------------------------------------------------------

    def load_enabled(self) -> None:
        """Load every enabled, fully-granted plugin into the registry."""
        self.discover()
        for pid, manifest in self.manifests.items():
            if not self.is_enabled(pid):
                continue
            missing = set(manifest.permissions) - self.granted_permissions(pid)
            if missing:
                self.errors[pid] = f"missing permissions: {', '.join(sorted(missing))}"
                continue
            self._load_one(manifest)

    def _load_one(self, manifest: PluginManifest) -> None:
        if manifest.id in self.loaded:
            return  # already loaded this run
        entry = manifest.path / manifest.entry
        if not entry.exists():
            self.errors[manifest.id] = f"entry file {manifest.entry} not found"
            return
        # Refuse to run code the user hasn't approved: the hash pinned at
        # enable time must match the entry file on disk. A change (edit,
        # update, tampering) requires an explicit re-enable to re-approve.
        current = self.code_hash(manifest)
        approved = self.approved_hash(manifest.id)
        if approved != current:
            self.errors[manifest.id] = (
                "plugin code changed since it was approved — disable and re-enable "
                "it to review and approve the new version"
            )
            log.warning(
                "plugin_hash_mismatch", plugin=manifest.id, approved=approved, current=current
            )
            return
        try:
            spec = importlib.util.spec_from_file_location(f"corvus_plugin_{manifest.id}", entry)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "register"):
                raise PluginError("plugin has no register(ctx) function")
            ctx = PluginContext(manifest, self.registry, self.granted_permissions(manifest.id))
            module.register(ctx)
            self.loaded[manifest.id] = ctx.registered_actions
            self.errors.pop(manifest.id, None)
            log.info("plugin_loaded", plugin=manifest.id, actions=len(ctx.registered_actions))
        except Exception as exc:  # noqa: BLE001 - a bad plugin must not crash Corvus
            self.errors[manifest.id] = str(exc)
            log.warning("plugin_load_failed", plugin=manifest.id, error=str(exc))

    # -- listing --------------------------------------------------------------

    def catalog(self) -> list[dict]:
        self.discover()
        out = []
        for pid, m in sorted(self.manifests.items()):
            out.append({
                "id": pid,
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "author": m.author,
                "permissions": m.permissions,
                "enabled": self.is_enabled(pid),
                "granted_permissions": sorted(self.granted_permissions(pid)),
                "loaded": pid in self.loaded,
                "actions": self.loaded.get(pid, []),
                "error": self.errors.get(pid),
                "bundled": (m.path.parent == _BUNDLED),
                "code_hash": self.code_hash(m),
            })
        return out
