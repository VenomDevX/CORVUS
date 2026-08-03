"""Post-turn memory extraction.

After each assistant turn, a bounded second LLM call decides whether the
exchange contained ONE durable fact worth remembering (a preference, project,
person, or favorite app). Anything stored appears in the Memory sidebar view
and is user-deletable - nothing is logged silently.
"""

import json
import re

import structlog

from ..llm.base import Message
from ..llm.ollama import OllamaProvider
from .repository import MEMORY_CATEGORIES, Repository

log = structlog.get_logger("corvus")

EXTRACTION_PROMPT = """You maintain the long-term memory of Corvus, a desktop assistant.
Given one exchange between the user and the assistant, decide whether it reveals a durable
fact about the user worth remembering across future conversations.

Only store facts of these kinds:
- preference: a lasting like/dislike or way the user wants things done
- project: an ongoing project or goal the user is working on
- person: a person the user refers to by name and relationship
- app: an application or tool the user regularly uses

Respond with ONLY a JSON object, no prose:
{"store": true, "category": "preference|project|person|app", "content": "<one short sentence>"}
or {"store": false}

Do NOT store small talk, one-off questions, technical content of answers, or anything speculative."""


def _parse(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def extract_memory(
    provider: OllamaProvider,
    model: str,
    repo: Repository,
    user_text: str,
    assistant_text: str,
    conversation_id: int,
) -> dict | None:
    """Run one extraction pass; returns the stored memory row or None."""
    clean_user = user_text.strip().lower()
    if len(clean_user) < 12 or clean_user in {
        "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "yes", "no", "bye", "cool", "great"
    }:
        return None

    exchange = f"User: {user_text}\nAssistant: {assistant_text[:1000]}"
    try:
        raw = await provider.complete(
            [Message("system", EXTRACTION_PROMPT), Message("user", exchange)], model
        )
    except Exception as exc:
        log.warning("memory_extraction_failed", error=str(exc))
        return None

    parsed = _parse(raw)
    if not parsed or not parsed.get("store"):
        return None
    category = parsed.get("category")
    content = str(parsed.get("content", "")).strip()
    if category not in MEMORY_CATEGORIES or not content or len(content) > 300:
        return None
    if repo.memory_exists(content):
        return None
    row = repo.add_memory(category, content, conversation_id)
    log.info("memory_stored", category=category, memory_id=row["id"])
    return row
