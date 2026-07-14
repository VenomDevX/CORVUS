"""Text-to-speech for Corvus.

Primary engine: Microsoft Edge neural voices via edge-tts (natural female
voice, default en-US-AriaNeural) with light emotion-aware prosody hints.
Fallback: Windows SAPI (pyttsx3) when offline.

Streaming design: assistant tokens feed a SentenceChunker; each completed
sentence is synthesized and played immediately, so speech starts well before
the full response exists. Playback checks an interrupt Event between small
chunks, making speech stoppable mid-sentence (barge-in).
"""

import asyncio
import re
import threading
from collections.abc import Callable

import numpy as np
import structlog

log = structlog.get_logger("corvus")

DEFAULT_VOICE = "en-US-AriaNeural"

# Sentence boundary = terminal punctuation followed by whitespace. End-of-buffer
# is NOT a boundary mid-stream (the next token could extend "3." into "3.14");
# whatever remains is released by flush() once the stream truly ends.
_SENTENCE_END = re.compile(r"([.!?…]+[\"')\]]?)\s")


class SentenceChunker:
    """Incrementally splits a token stream into speakable sentences."""

    def __init__(self, min_chars: int = 12):
        self._buffer = ""
        self.min_chars = min_chars

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        out: list[str] = []
        while True:
            match = _SENTENCE_END.search(self._buffer)
            if not match:
                break
            end = match.end(1)
            candidate = self._buffer[:end].strip()
            rest = self._buffer[end:]
            if len(candidate) < self.min_chars and out:
                # Glue very short fragments ("Yes.") onto the previous sentence.
                out[-1] = f"{out[-1]} {candidate}"
            elif candidate:
                out.append(candidate)
            self._buffer = rest.lstrip()
        return out

    def flush(self) -> str | None:
        rest = self._buffer.strip()
        self._buffer = ""
        return rest or None


def prosody_for(text: str) -> tuple[str, str]:
    """(rate, pitch) hints from surface cues - emotion-aware inflection."""
    if text.rstrip().endswith("!"):
        return "+8%", "+12Hz"
    if text.rstrip().endswith("?"):
        return "+2%", "+18Hz"
    return "+0%", "+0Hz"


def _strip_markdown(text: str) -> str:
    """Code fences, inline markup, and links read terribly aloud - drop them."""
    text = re.sub(r"```.*?```", " code block omitted. ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class EdgeSpeaker:
    """edge-tts synthesis + sounddevice playback."""

    name = "edge"

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        rate, pitch = prosody_for(text)
        communicate = edge_tts.Communicate(text, voice=self.voice, rate=rate, pitch=pitch)
        parts: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                parts.append(chunk["data"])
        return b"".join(parts)

    def _play_sync(
        self,
        mp3: bytes,
        on_level: Callable[[float], None],
        interrupt: threading.Event,
    ) -> bool:
        import miniaudio
        import sounddevice as sd

        decoded = miniaudio.decode(mp3, nchannels=1, sample_rate=24000)
        samples = np.asarray(decoded.samples, dtype=np.int16)
        chunk = 24000 // 20  # 50 ms
        with sd.OutputStream(samplerate=24000, channels=1, dtype="int16") as stream:
            for start in range(0, len(samples), chunk):
                if interrupt.is_set():
                    return False
                block = samples[start : start + chunk]
                stream.write(block.reshape(-1, 1))
                on_level(float(np.sqrt(np.mean((block / 32768.0) ** 2))) if block.size else 0.0)
        return True

    async def speak(
        self,
        text: str,
        on_level: Callable[[float], None],
        interrupt: threading.Event,
    ) -> bool:
        """Speak one sentence; returns False if interrupted."""
        clean = _strip_markdown(text)
        if not clean:
            return True
        mp3 = await self.synthesize(clean)
        if interrupt.is_set():
            return False
        return await asyncio.to_thread(self._play_sync, mp3, on_level, interrupt)


class SapiSpeaker:
    """Offline fallback: Windows SAPI via pyttsx3 (prefers a female voice)."""

    name = "sapi"

    def _speak_sync(self, text: str, interrupt: threading.Event) -> bool:
        import pyttsx3

        engine = pyttsx3.init()
        for voice in engine.getProperty("voices"):
            if "zira" in voice.name.lower() or "female" in voice.name.lower():
                engine.setProperty("voice", voice.id)
                break
        if interrupt.is_set():
            return False
        engine.say(text)
        engine.runAndWait()
        return not interrupt.is_set()

    async def speak(
        self,
        text: str,
        on_level: Callable[[float], None],
        interrupt: threading.Event,
    ) -> bool:
        clean = _strip_markdown(text)
        if not clean:
            return True
        on_level(0.5)
        result = await asyncio.to_thread(self._speak_sync, clean, interrupt)
        on_level(0.0)
        return result


class Speaker:
    """Edge-first speaker with automatic SAPI fallback when offline."""

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.edge = EdgeSpeaker(voice)
        self.sapi = SapiSpeaker()

    @property
    def voice(self) -> str:
        return self.edge.voice

    @voice.setter
    def voice(self, value: str) -> None:
        self.edge.voice = value

    async def speak(
        self,
        text: str,
        on_level: Callable[[float], None],
        interrupt: threading.Event,
    ) -> bool:
        try:
            return await self.edge.speak(text, on_level, interrupt)
        except Exception as exc:
            log.warning("tts_edge_failed_falling_back", error=str(exc))
            return await self.sapi.speak(text, on_level, interrupt)
