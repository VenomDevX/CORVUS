from corvus.session import SessionManager


def test_clean_run_is_not_flagged_as_recovered(repo):
    s = SessionManager(repo)
    s.begin()
    assert s.recovered is False
    s.end()

    # A second manager after a clean end() must not report recovery.
    s2 = SessionManager(repo)
    s2.begin()
    assert s2.recovered is False
    s2.end()


def test_unclean_shutdown_detected(repo):
    s = SessionManager(repo)
    s.begin()
    # ...crash: end() never called. A new manager sees the stale running flag.
    s2 = SessionManager(repo)
    s2.begin()
    assert s2.recovered is True


def test_active_conversation_restore(repo):
    conv = repo.create_conversation("chat")
    s = SessionManager(repo)
    s.set_active_conversation(conv["id"])
    assert s.active_conversation() == conv["id"]
    assert s.state()["active_conversation"] == conv["id"]


def test_active_conversation_ignored_if_deleted(repo):
    conv = repo.create_conversation("chat")
    s = SessionManager(repo)
    s.set_active_conversation(conv["id"])
    repo.delete_conversation(conv["id"])
    assert s.active_conversation() is None


def test_clearing_active_conversation(repo):
    s = SessionManager(repo)
    s.set_active_conversation(5)
    s.set_active_conversation(None)
    assert s.active_conversation() is None
