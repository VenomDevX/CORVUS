"""Speech-to-text on faster-whisper (local, offline).

English default, but language is a parameter end to end - adding languages
later means passing a different code (or None for auto-detect), not a rewrite.
Models load lazily in a worker thread so service startup stays fast.
"""

import asyncio
import threading
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger("corvus")


class Transcriber:
    _model_cache: dict[str, Any] = {}
    _cache_lock = threading.Lock()

    def __init__(self, model_name: str = "base.en", language: str = "en"):
        self.model_name = model_name
        self.language = language

    def _ensure_model(self):
        with Transcriber._cache_lock:
            if self.model_name not in Transcriber._model_cache:
                from faster_whisper import WhisperModel

                log.info("stt_model_loading", model=self.model_name)
                Transcriber._model_cache[self.model_name] = WhisperModel(
                    self.model_name, device="cpu", compute_type="int8"
                )
                log.info("stt_model_ready", model=self.model_name)
            return Transcriber._model_cache[self.model_name]

    def transcribe_sync(self, audio: np.ndarray, language: str | None = None) -> str:
        """Blocking transcription of float32 16 kHz mono audio."""
        if audio.size < 1600:  # <0.1 s of audio - nothing to hear
            return ""
        model = self._ensure_model()
        segments, _info = model.transcribe(
            audio,
            language=language or self.language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    async def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        return await asyncio.to_thread(self.transcribe_sync, audio, language)
