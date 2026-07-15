"""Session tracking and crash recovery.

Corvus persists a little session state so a crash mid-task doesn't lose the
user's place: the active conversation is remembered and restored on the next
launch, and an unclean shutdown is detected (the previous run never cleared its
"running" flag) so the app can tell the user it recovered.

Durable work already survives independently - conversations, memories,
reminders, and workflows are all in SQLite; this adds the transient
"where was I" layer on top.
"""

import structlog

log = structlog.get_logger("corvus")

_RUNNING = "session:running"
_ACTIVE_CONVERSATION = "session:active_conversation"


class SessionManager:
    def __init__(self, repo):
        self.repo = repo
        self.recovered = False

    def begin(self) -> None:
        """Mark the session running; detect an unclean previous shutdown."""
        if self.repo.get_setting(_RUNNING) == "true":
            # The last run set this and never cleared it -> it crashed.
            self.recovered = True
            log.warning("unclean_shutdown_detected")
        self.repo.set_setting(_RUNNING, "true")

    def end(self) -> None:
        self.repo.set_setting(_RUNNING, "false")

    def set_active_conversation(self, conversation_id: int | None) -> None:
        self.repo.set_setting(_ACTIVE_CONVERSATION, str(conversation_id) if conversation_id else "")

    def active_conversation(self) -> int | None:
        raw = self.repo.get_setting(_ACTIVE_CONVERSATION)
        if raw and raw.isdigit():
            # Only restore it if it still exists.
            if self.repo.get_conversation(int(raw)):
                return int(raw)
        return None

    def state(self) -> dict:
        return {
            "recovered": self.recovered,
            "active_conversation": self.active_conversation(),
        }
