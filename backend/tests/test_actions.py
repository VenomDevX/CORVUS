import pytest

from corvus.actions.files import PathNotAllowed
from corvus.actions.registry import ActionResult, ActionSpec, Registry, Risk
from corvus.actions.registry import build_default_registry


def test_default_registry_covers_categories():
    reg = build_default_registry()
    cats = {a.category for a in reg.all()}
    for expected in ["apps", "power", "audio", "display", "media", "search", "files",
                     "software", "clipboard", "monitoring"]:
        assert expected in cats


def test_every_confirmable_action_has_specific_prompt():
    reg = build_default_registry()
    for spec in reg.all():
        if spec.requires_confirmation:
            prompt = spec.describe_confirmation({"path": "x", "package_id": "y", "src": "a", "dest": "b", "new_name": "n"})
            assert prompt and prompt != "Are you sure?"
            assert "?" in prompt  # states a specific question


def test_delete_confirmation_names_the_target():
    reg = build_default_registry()
    prompt = reg.get("delete_item").describe_confirmation({"path": "report.docx"})
    assert "report.docx" in prompt
    assert "recycle bin" in prompt.lower()


def test_risk_tiers_gate_confirmation():
    reg = build_default_registry()
    assert reg.get("system_status").requires_confirmation is False  # SAFE
    assert reg.get("open_app").requires_confirmation is False        # LOW
    assert reg.get("create_folder").requires_confirmation is True    # MEDIUM
    assert reg.get("shutdown_windows").requires_confirmation is True  # HIGH


def test_registry_rejects_confirmable_without_prompt():
    reg = Registry()
    with pytest.raises(ValueError, match="confirm_prompt"):
        reg.register(ActionSpec("bad", "d", {}, Risk.HIGH, lambda: None))


async def test_execute_wraps_handler_errors():
    reg = Registry()
    reg.register(ActionSpec("boom", "d", {"type": "object", "properties": {}}, Risk.SAFE,
                            lambda: (_ for _ in ()).throw(RuntimeError("nope"))))
    result = await reg.execute("boom", {})
    assert result.ok is False
    assert "nope" in result.message


async def test_execute_unknown_action():
    reg = Registry()
    result = await reg.execute("ghost", {})
    assert result.ok is False


async def test_async_and_sync_handlers():
    reg = Registry()
    reg.register(ActionSpec("sync", "d", {"type": "object", "properties": {}}, Risk.SAFE,
                            lambda: ActionResult(True, "sync ok")))

    async def ahandler():
        return ActionResult(True, "async ok")

    reg.register(ActionSpec("async", "d", {"type": "object", "properties": {}}, Risk.SAFE, ahandler))
    assert (await reg.execute("sync", {})).message == "sync ok"
    assert (await reg.execute("async", {})).message == "async ok"


def test_safe_path_blocks_escape(tmp_path, monkeypatch):
    import corvus.actions.files as f
    monkeypatch.setattr(f, "USER_ROOT", tmp_path.resolve())
    inside = f.safe_path("subdir/file.txt")
    assert tmp_path.resolve() in inside.parents
    with pytest.raises(PathNotAllowed):
        f.safe_path("C:/Windows/System32/evil.dll")


def test_safe_path_maps_made_up_home_folders(tmp_path, monkeypatch):
    # Local models write "C:\Users\YourUsername\Desktop\x"; that user doesn't
    # exist, so it means this user's home. A real other user's folder doesn't.
    import corvus.actions.files as f
    home = tmp_path / "Users" / "me"
    (tmp_path / "Users" / "Public").mkdir(parents=True)
    home.mkdir()
    monkeypatch.setattr(f, "USER_ROOT", home.resolve())
    assert f.safe_path(r"C:\Users\<YourUsername>\Desktop\x") == home.resolve() / "Desktop" / "x"
    assert f.safe_path("/Users/your-username/Downloads") == home.resolve() / "Downloads"
    assert f.shown(r"C:\Users\YourUsername\Desktop") == str(home.resolve() / "Desktop")
    assert f._unalias_home("C:/Users/Public/x") == "C:/Users/Public/x"  # exists: not mapped
