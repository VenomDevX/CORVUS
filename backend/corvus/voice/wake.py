"""Local wake-word detection for "Hey Corvus" / "Corvus".

Default implementation transcribes short VAD-gated windows with a tiny local
Whisper model and fuzzy-matches the wake phrase - fully offline, no keys, no
cloud. The WakeDetector protocol keeps this swappable for a dedicated
keyword-spotting model (Porcupine/openWakeWord) without pipeline changes.
"""

import re
from typing import Protocol

import numpy as np

from .stt import Transcriber

# Common Whisper mishearings of "corvus" on short windows.
WAKE_PATTERNS = [
    r"\bcorvus\b",
    r"\bcorvis\b",
    r"\bcorpus\b",
    r"\bcorvos\b",
    r"\bkorvus\b",
    r"\bcore\s?vu?s\b",
]
_WAKE_RE = re.compile("|".join(WAKE_PATTERNS), re.IGNORECASE)


def matches_wake_phrase(text: str) -> bool:
    return bool(_WAKE_RE.search(text))


class WakeDetector(Protocol):
    async def detect(self, audio: np.ndarray) -> bool:
        """True if the wake phrase occurs in this short audio window."""
        ...


class WhisperWakeDetector:
    def __init__(self, transcriber: Transcriber | None = None):
        # tiny.en keeps the always-on path cheap; independent of the main STT model.
        self._transcriber = transcriber or Transcriber(model_name="tiny.en")

    async def detect(self, audio: np.ndarray) -> bool:
        # Cap the window at 3 s - wake checks must stay snappy.
        text = await self._transcriber.transcribe(audio[-3 * 16000 :])
        return matches_wake_phrase(text)
