import json

import pytest

from corvus.actions.registry import Registry
from corvus.plugins.manager import PluginManager
from corvus.plugins.sdk import PluginError, PluginManifest


@pytest.fixture
def manager(repo):
    return PluginManager(repo, Registry())


def test_discovers_bundled_plugins(manager):
    manager.discover()
    assert "text-tools" in manager.manifests
    assert "web-peek" in manager.manifests


def test_enable_permission_free_plugin_loads_actions(manager):
    manager.discover()
    result = manager.enable("text-tools")
    assert result["loaded"] is True
    names = {a.name for a in manager.registry.all()}
    assert "text-tools.word_count" in names
    assert "text-tools.reverse" in names


def test_plugin_needing_permission_not_loaded_until_granted(manager):
    manager.discover()
    manager.enable("web-peek")
    assert not any("web-peek" in a.name for a in manager.registry.all())

    manager.set_permissions("web-peek", ["network"])
    assert any(a.name == "web-peek.page_title" for a in manager.registry.all())


def test_disable_removes_actions(manager):
    manager.discover()
    manager.enable("text-tools")
    assert any("text-tools" in a.name for a in manager.registry.all())
    manager.disable("text-tools")
    assert not any("text-tools" in a.name for a in manager.registry.all())


async def test_plugin_action_runs(manager):
    manager.discover()
    manager.enable("text-tools")
    result = await manager.registry.execute("text-tools.word_count", {"text": "hey there corvus"})
    assert result.ok
    assert result.data["words"] == 3


def test_catalog_reports_state(manager):
    manager.discover()
    manager.enable("text-tools")
    catalog = {p["id"]: p for p in manager.catalog()}
    assert catalog["text-tools"]["enabled"] is True
    assert catalog["text-tools"]["loaded"] is True
    assert catalog["web-peek"]["permissions"] == ["network"]
    assert catalog["text-tools"]["bundled"] is True


def _write_user_plugin(manager, body: str, pid: str = "hashy") -> None:
    d = manager.user_dir() / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({
        "id": pid, "name": "Hashy", "version": "1", "description": "d", "author": "a",
        "permissions": [],
    }))
    (d / "plugin.py").write_text(body)


_PLUGIN_V1 = (
    "def register(ctx):\n"
    "    ctx.action('ping', 'ping', {'type': 'object', 'properties': {}},\n"
    "               lambda: {'ok': True})\n"
)
_PLUGIN_V2 = _PLUGIN_V1 + "# changed\n"


def test_code_change_blocks_load_until_reapproved(manager, repo):
    _write_user_plugin(manager, _PLUGIN_V1)
    manager.discover()
    assert manager.enable("hashy")["loaded"] is True

    # The code changes on disk; a fresh manager (new app run) must refuse it.
    _write_user_plugin(manager, _PLUGIN_V2)
    fresh = PluginManager(repo, Registry())
    fresh.load_enabled()
    assert "hashy" not in fresh.loaded
    assert "changed" in fresh.errors["hashy"]
    assert not any("hashy" in a.name for a in fresh.registry.all())

    # Re-enabling is the re-approval: it pins the new hash and loads.
    assert fresh.enable("hashy")["loaded"] is True


def test_catalog_exposes_code_hash(manager):
    manager.discover()
    catalog = {p["id"]: p for p in manager.catalog()}
    h = catalog["text-tools"]["code_hash"]
    assert isinstance(h, str) and len(h) == 64


def _zip_bytes(entries: dict[str, str]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _plugin_zip(pid: str = "zippy", prefix: str = "") -> bytes:
    manifest = json.dumps({
        "id": pid, "name": "Zippy", "version": "1", "description": "d", "author": "a",
        "permissions": [],
    })
    return _zip_bytes({
        f"{prefix}manifest.json": manifest,
        f"{prefix}plugin.py": _PLUGIN_V1,
    })


def test_install_zip_from_root(manager):
    manifest = manager.install_zip(_plugin_zip())
    assert manifest.id == "zippy"
    catalog = {p["id"]: p for p in manager.catalog()}
    assert catalog["zippy"]["enabled"] is False
    assert catalog["zippy"]["bundled"] is False
    assert manager.enable("zippy")["loaded"] is True


def test_install_zip_with_top_level_folder(manager):
    manifest = manager.install_zip(_plugin_zip(prefix="zippy-main/"))
    assert manifest.id == "zippy"
    assert (manager.user_dir() / "zippy" / "plugin.py").exists()


def test_install_rejects_zip_slip(manager):
    bad = _zip_bytes({"../evil.py": "x", "manifest.json": "{}"})
    with pytest.raises(PluginError, match="unsafe path"):
        manager.install_zip(bad)


def test_install_rejects_missing_manifest(manager):
    with pytest.raises(PluginError, match="manifest.json"):
        manager.install_zip(_zip_bytes({"plugin.py": "x"}))


def test_install_rejects_bundled_id(manager):
    with pytest.raises(PluginError, match="built-in"):
        manager.install_zip(_plugin_zip(pid="text-tools"))


def test_install_rejects_garbage(manager):
    with pytest.raises(PluginError, match="zip"):
        manager.install_zip(b"not a zip")


def test_install_rejects_traversal_id(manager):
    manifest = json.dumps({
        "id": "../evil", "name": "E", "version": "1", "description": "d", "author": "a",
        "permissions": [],
    })
    with pytest.raises(PluginError, match="kebab-case"):
        manager.install_zip(_zip_bytes({"manifest.json": manifest, "plugin.py": "x"}))


def test_install_rejects_entry_escape(manager):
    manifest = json.dumps({
        "id": "sneaky", "name": "S", "version": "1", "description": "d", "author": "a",
        "permissions": [], "entry": "../outside.py",
    })
    with pytest.raises(PluginError, match="entry file"):
        manager.install_zip(_zip_bytes({"manifest.json": manifest, "plugin.py": "x"}))


def test_upgrade_requires_reapproval(manager):
    manager.install_zip(_plugin_zip())
    assert manager.enable("zippy")["loaded"] is True
    manager.install_zip(_plugin_zip())  # reinstall = upgrade
    catalog = {p["id"]: p for p in manager.catalog()}
    assert catalog["zippy"]["enabled"] is False
    assert catalog["zippy"]["loaded"] is False


def test_uninstall_user_plugin(manager):
    manager.install_zip(_plugin_zip())
    manager.enable("zippy")
    assert manager.uninstall("zippy") is True
    assert "zippy" not in manager.manifests
    assert not (manager.user_dir() / "zippy").exists()
    assert not any("zippy" in a.name for a in manager.registry.all())


def test_uninstall_bundled_refused(manager):
    assert manager.uninstall("text-tools") is False
    assert manager.uninstall("nope") is False


def test_manifest_validation(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"id": "x", "name": "X"}))
    with pytest.raises(PluginError, match="missing"):
        PluginManifest.load(tmp_path)

    (tmp_path / "manifest.json").write_text(json.dumps({
        "id": "x", "name": "X", "version": "1", "description": "d", "author": "a",
        "permissions": ["telepathy"],
    }))
    with pytest.raises(PluginError, match="unknown permission"):
        PluginManifest.load(tmp_path)
