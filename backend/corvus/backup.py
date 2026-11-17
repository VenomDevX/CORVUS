"""Passphrase-encrypted export/import of the user's Corvus data.

At rest, Corvus encrypts with a DPAPI-bound key - unreadable on another PC or
Windows profile. A backup must be portable, so it decrypts the rows and
re-encrypts the bundle with a key derived from the user's passphrase (scrypt)
and Fernet. API keys are never exported (they stay in this profile's vault).
# ponytail: generated media files are not included, only their database rows'
# text lives in the media DB; add a zip payload if users ask for media backups.
"""

from __future__ import annotations

import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import __version__

MAGIC = b"CORVUSBAK1"
SALT_BYTES = 16
MIN_PASSPHRASE = 8
# Settings that are safe and useful to carry across machines.
PORTABLE_SETTINGS = ("provider", "tts_voice", "onboarding_complete", "rag_folder")


class BackupError(Exception):
    pass


def _fernet(passphrase: str, salt: bytes) -> Fernet:
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8"))))


def export_bundle(repo, passphrase: str) -> bytes:
    if len(passphrase) < MIN_PASSPHRASE:
        raise BackupError(f"use a passphrase of at least {MIN_PASSPHRASE} characters")
    conversations = []
    for convo in repo.list_conversations():
        conversations.append({
            "title": convo["title"],
            "created_at": convo["created_at"],
            "messages": [
                {"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                for m in repo.list_messages(convo["id"])
            ],
        })
    payload = {
        "app": "Corvus",
        "version": __version__,
        "conversations": conversations,
        "memories": [{"category": m["category"], "content": m["content"]} for m in repo.list_memories()],
        "workflows": [
            {"name": w["name"], "steps": json.loads(w["steps"]), "trigger_type": w["trigger_type"],
             "trigger_config": json.loads(w["trigger_config"])}
            for w in repo.list_workflows()
        ],
        "reminders": [
            {"text": r["text"], "kind": r["kind"], "fire_at": r["fire_at"]}
            for r in repo.pending_reminders()
        ],
        "settings": {k: v for k in PORTABLE_SETTINGS if (v := repo.get_setting(k)) is not None},
    }
    salt = os.urandom(SALT_BYTES)
    token = _fernet(passphrase, salt).encrypt(json.dumps(payload).encode("utf-8"))
    return MAGIC + salt + token


def read_bundle(data: bytes, passphrase: str) -> dict:
    if not data.startswith(MAGIC) or len(data) <= len(MAGIC) + SALT_BYTES:
        raise BackupError("this isn't a Corvus backup file")
    salt = data[len(MAGIC):len(MAGIC) + SALT_BYTES]
    try:
        raw = _fernet(passphrase, salt).decrypt(data[len(MAGIC) + SALT_BYTES:])
    except InvalidToken as exc:
        raise BackupError("wrong passphrase, or the backup is damaged") from exc
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("app") != "Corvus":
        raise BackupError("this isn't a Corvus backup file")
    return payload


def import_bundle(repo, workflows, data: bytes, passphrase: str, hub=None) -> dict:
    """Merge a backup into the current data: conversations and memories are
    appended (duplicate memories skipped), workflows upserted through the
    engine so its risk rules still apply, reminders re-added."""
    payload = read_bundle(data, passphrase)
    counts = {"conversations": 0, "memories": 0, "workflows": 0, "reminders": 0, "skipped": 0}
    for convo in payload.get("conversations", []):
        new = repo.create_conversation(str(convo.get("title") or "Imported chat"))
        for m in convo.get("messages", []):
            if m.get("role") in ("user", "assistant"):
                repo.add_message(new["id"], m["role"], str(m.get("content", "")))
        counts["conversations"] += 1
    for mem in payload.get("memories", []):
        try:
            if not repo.memory_exists(str(mem.get("content", ""))):
                repo.add_memory(mem.get("category"), str(mem.get("content", "")))
                counts["memories"] += 1
        except ValueError:
            counts["skipped"] += 1
    for wf in payload.get("workflows", []):
        try:
            workflows.create(wf["name"], wf["steps"], wf.get("trigger_type", "manual"),
                             wf.get("trigger_config") or {})
            counts["workflows"] += 1
        except Exception:  # noqa: BLE001 - an action this install lacks: skip that workflow
            counts["skipped"] += 1
    from datetime import datetime

    for rem in payload.get("reminders", []):
        text, kind = str(rem.get("text", "")), str(rem.get("kind", "reminder"))
        try:
            fire_at = datetime.fromisoformat(str(rem["fire_at"]))
        except (KeyError, ValueError):
            counts["skipped"] += 1
            continue
        if hub is not None:
            hub.schedule(text, kind, fire_at)  # live: fires this session
        else:
            repo.add_reminder(text, kind, fire_at.isoformat(timespec="seconds"))
        counts["reminders"] += 1
    for key, value in (payload.get("settings") or {}).items():
        if key in PORTABLE_SETTINGS and key != "provider":
            repo.set_setting(key, str(value))
    return counts
