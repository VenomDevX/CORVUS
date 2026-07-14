import pytest

from corvus.memory.repository import Repository


def test_conversation_crud(repo: Repository):
    conv = repo.create_conversation("Test chat")
    assert conv["id"] == 1
    assert conv["title"] == "Test chat"

    assert [c["id"] for c in repo.list_conversations()] == [1]
    assert repo.get_conversation(1)["title"] == "Test chat"

    assert repo.delete_conversation(1) is True
    assert repo.delete_conversation(1) is False
    assert repo.list_conversations() == []


def test_messages_ordered_and_cascade(repo: Repository):
    conv = repo.create_conversation("c")
    repo.add_message(conv["id"], "user", "hi")
    repo.add_message(conv["id"], "assistant", "hello")

    messages = repo.list_messages(conv["id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]

    repo.delete_conversation(conv["id"])
    assert repo.list_messages(conv["id"]) == []


def test_memory_crud_and_validation(repo: Repository):
    conv = repo.create_conversation("c")
    row = repo.add_memory("preference", "Prefers dark mode", conv["id"])
    assert row["category"] == "preference"
    assert repo.memory_exists("prefers DARK mode")  # case-insensitive dedupe

    with pytest.raises(ValueError):
        repo.add_memory("nonsense", "x")

    assert repo.delete_memory(row["id"]) is True
    assert repo.list_memories() == []


def test_memory_survives_conversation_delete(repo: Repository):
    conv = repo.create_conversation("c")
    repo.add_memory("project", "Building Corvus", conv["id"])
    repo.delete_conversation(conv["id"])
    memories = repo.list_memories()
    assert len(memories) == 1
    assert memories[0]["source_conversation"] is None


def test_settings_upsert(repo: Repository):
    assert repo.get_setting("model") is None
    assert repo.get_setting("model", "default") == "default"
    repo.set_setting("model", "a")
    repo.set_setting("model", "b")
    assert repo.get_setting("model") == "b"
