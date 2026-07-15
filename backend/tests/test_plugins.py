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
