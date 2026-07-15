"""The Corvus voice pipeline.

One always-on state machine: idle (wake watch) -> listening -> thinking ->
speaking -> idle. Frames flow from a mic source; events flow out to WebSocket
subscribers (state, levels, transcripts, assistant deltas). Speech output is
sentence-streamed and interruptible - sustained user speech during playback
(barge-in) stops Corvus mid-sentence and starts a new listen.

Audio hardware, STT, TTS, and wake detection are all injected, so the whole
machine is testable with fakes.
"""

import asyncio
import contextlib
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np
import structlog

from ..config import SYSTEM_PROMPT
from ..llm.base import Message
from ..memory.extractor import extract_memory
from .stt import Transcriber
from .tts import SentenceChunker, Speaker
from .vad import FRAME_SAMPLES, EnergyVAD, Segmenter, rms
from .wake import WakeDetector, WhisperWakeDetector

log = structlog.get_logger("corvus")

MAX_HISTORY_MESSAGES = 40
BARGE_IN_MIN_LEVEL = 0.03
BARGE_IN_FRAMES = 10  # ~300 ms of sustained speech interrupts playback


class MicSource(Protocol):
    def start(self, on_frame: Callable[[np.ndarray], None]) -> None: ...
    def stop(self) -> None: ...


class SoundDeviceMic:
    """16 kHz mono float32 capture via PortAudio."""

    def __init__(self) -> None:
        self._stream = None

    def start(self, on_frame: Callable[[np.ndarray], None]) -> None:
        import sounddevice as sd

        def callback(indata, _frames, _time, status):
            if status:
                log.warning("mic_status", status=str(status))
            on_frame(indata[:, 0].copy())

        self._stream = sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype="float32",
            blocksize=FRAME_SAMPLES,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class VoicePipeline:
    def __init__(
        self,
        repo,
        provider,
        mic: MicSource | None = None,
        transcriber: Transcriber | None = None,
        speaker: Speaker | None = None,
        wake: WakeDetector | None = None,
        workflows=None,
    ) -> None:
        self.repo = repo
        self.provider = provider
        self.workflows = workflows
        self.mic = mic if mic is not None else SoundDeviceMic()
        self.transcriber = transcriber or Transcriber(model_name="base.en")
        self.speaker = speaker or Speaker()
        saved_voice = repo.get_setting("tts_voice")
        if saved_voice:
            self.speaker.voice = saved_voice
        self.wake = wake or WhisperWakeDetector()

        self.state = "off"
        self.available = False
        self.wake_enabled = repo.get_setting("wake_enabled", "true") == "true"
        self.conversation_id: int | None = None

        self._subscribers: set[asyncio.Queue] = set()
        self._frames: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=256)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task | None = None
        self._turn_task: asyncio.Task | None = None
        self._interrupt = threading.Event()
        self._ptt_requested = asyncio.Event()
        self._level_frame_count = 0

    # -- events --------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def emit(self, event: dict) -> None:
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    def _emit_threadsafe(self, event: dict) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.emit, event)

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            log.info("voice_state", state=state)
        self.emit({"type": "state", "state": state, "conversation_id": self.conversation_id})

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()

        def on_frame(frame: np.ndarray) -> None:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._push_frame, frame)

        try:
            self.mic.start(on_frame)
        except Exception as exc:
            self.available = False
            self.state = "unavailable"
            log.error("voice_unavailable", error=str(exc))
            self.emit({"type": "unavailable", "reason": str(exc)})
            return

        self.available = True
        self._set_state("idle")
        self._main_task = asyncio.create_task(self._run())
        log.info("voice_pipeline_started", wake_enabled=self.wake_enabled)

    async def stop(self) -> None:
        self._interrupt.set()
        if self._main_task:
            self._main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._main_task
        with contextlib.suppress(Exception):
            self.mic.stop()
        self.state = "off"

    def _push_frame(self, frame: np.ndarray) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            self._frames.put_nowait(frame)

    # -- commands (from the WS API) -------------------------------------------

    def set_wake_enabled(self, enabled: bool) -> None:
        self.wake_enabled = enabled
        self.repo.set_setting("wake_enabled", "true" if enabled else "false")
        self.emit({"type": "wake_enabled", "enabled": enabled})
        log.info("wake_toggled", enabled=enabled)

    def push_to_talk(self) -> None:
        """Start listening now (mic button)."""
        if self.state == "speaking":
            self._interrupt.set()
        self._ptt_requested.set()

    def stop_speaking(self) -> None:
        self._interrupt.set()

    # -- main loop -------------------------------------------------------------

    async def _run(self) -> None:
        wake_segmenter = Segmenter(vad=EnergyVAD(), tail_ms=500, max_ms=4000)
        while True:
            if self._ptt_requested.is_set():
                self._ptt_requested.clear()
                await self._conversation_turn(reason="ptt")
                wake_segmenter.reset()
                continue

            try:
                frame = await asyncio.wait_for(self._frames.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            if not self.wake_enabled or self.state != "idle":
                continue

            event = wake_segmenter.feed(frame)
            if event == "close":
                audio = wake_segmenter.audio()
                wake_segmenter.reset()
                if await self.wake.detect(audio):
                    log.info("wake_detected")
                    self.emit({"type": "wake"})
                    await self._conversation_turn(reason="wake")
                    wake_segmenter.reset()

    def _drain_frames(self) -> None:
        while not self._frames.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._frames.get_nowait()

    async def _listen_for_utterance(self) -> np.ndarray | None:
        """Capture one utterance, emitting live input levels."""
        self._set_state("listening")
        self._drain_frames()
        segmenter = Segmenter()
        deadline = asyncio.get_running_loop().time() + 12.0  # give up if nobody speaks
        while True:
            try:
                frame = await asyncio.wait_for(self._frames.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if asyncio.get_running_loop().time() > deadline:
                    return None
                continue

            self._level_frame_count += 1
            if self._level_frame_count % 3 == 0:  # ~10 Hz level events
                self.emit({"type": "level", "value": round(min(1.0, rms(frame) * 12), 3)})

            event = segmenter.feed(frame)
            if event == "close":
                return segmenter.audio()
            if not segmenter.is_open and asyncio.get_running_loop().time() > deadline:
                return None

    async def _conversation_turn(self, reason: str) -> None:
        audio = await self._listen_for_utterance()
        if audio is None or audio.size == 0:
            self._set_state("idle")
            return

        self._set_state("thinking")
        text = await self.transcriber.transcribe(audio)
        if not text.strip():
            self._set_state("idle")
            return
        log.info("voice_transcript", chars=len(text), reason=reason)
        self.emit({"type": "transcript", "text": text})

        # A spoken phrase can trigger a saved workflow instead of a chat reply.
        if self.workflows is not None:
            matched = self.workflows.match_voice(text)
            if matched:
                self._set_state("thinking")
                self.emit({"type": "assistant_delta", "text": f"Running workflow “{matched}”…"})
                await self.workflows.run(matched)
                self.emit({"type": "assistant_done", "conversation_id": self.conversation_id})
                self._set_state("idle")
                return

        await self._respond(text)

    async def _respond(self, user_text: str) -> None:
        if self.conversation_id is None or self.repo.get_conversation(self.conversation_id) is None:
            title = f"Voice: {user_text[:50]}" + ("…" if len(user_text) > 50 else "")
            self.conversation_id = self.repo.create_conversation(title)["id"]
        self.repo.add_message(self.conversation_id, "user", user_text)
        self._set_state("thinking")

        history = self.repo.list_messages(self.conversation_id)[-MAX_HISTORY_MESSAGES:]
        messages = [Message("system", SYSTEM_PROMPT + "\nYou are in voice mode: keep replies short and conversational - a few sentences, no markdown, no code blocks unless asked to dictate code.")]
        messages += [Message(m["role"], m["content"]) for m in history]
        model = self._model()

        self._interrupt.clear()
        chunker = SentenceChunker()
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
        speak_task = asyncio.create_task(self._speak_loop(sentence_queue))

        parts: list[str] = []
        interrupted = False
        try:
            async for delta in self.provider.stream_chat(messages, model):
                if self._interrupt.is_set():
                    interrupted = True
                    break
                if delta.content:
                    parts.append(delta.content)
                    self.emit({"type": "assistant_delta", "text": delta.content})
                    for sentence in chunker.feed(delta.content):
                        sentence_queue.put_nowait(sentence)
            if not interrupted:
                tail = chunker.flush()
                if tail:
                    sentence_queue.put_nowait(tail)
        except Exception as exc:
            log.error("voice_turn_error", error=str(exc))
            self.emit({"type": "error", "message": f"Corvus couldn't reach the model: {exc}"})
        finally:
            sentence_queue.put_nowait(None)
            barge = await speak_task

        assistant_text = "".join(parts)
        if assistant_text:
            self.repo.add_message(self.conversation_id, "assistant", assistant_text)
        self.emit({"type": "assistant_done", "conversation_id": self.conversation_id})

        if barge:
            # The user talked over Corvus - listen to them right away.
            await self._conversation_turn(reason="barge-in")
            return

        self._set_state("idle")
        if assistant_text and not interrupted:
            await extract_memory(
                self.provider, self._model(), self.repo,
                user_text, assistant_text, self.conversation_id,
            )

    def _model(self) -> str:
        if hasattr(self.provider, "current_model"):
            return self.provider.current_model()
        return self.repo.get_setting("model") or self.repo.get_setting("model:ollama")

    async def _speak_loop(self, sentences: asyncio.Queue) -> bool:
        """Speak queued sentences while watching the mic for barge-in.

        Returns True if the user barged in.
        """
        speech_run = 0
        barge = False

        def on_level(value: float) -> None:
            self._emit_threadsafe({"type": "level", "value": round(min(1.0, value * 8), 3)})

        async def watch_mic() -> None:
            nonlocal speech_run, barge
            while True:
                frame = await self._frames.get()
                if rms(frame) > BARGE_IN_MIN_LEVEL:
                    speech_run += 1
                    if speech_run >= BARGE_IN_FRAMES:
                        barge = True
                        self._interrupt.set()
                        log.info("voice_barge_in")
                        return
                else:
                    speech_run = 0

        watcher: asyncio.Task | None = None
        spoke_anything = False
        try:
            while True:
                sentence = await sentences.get()
                if sentence is None:
                    return barge
                if self._interrupt.is_set():
                    continue  # drain remaining sentences without speaking
                if not spoke_anything:
                    self._set_state("speaking")
                    self._drain_frames()
                    watcher = asyncio.create_task(watch_mic())
                    spoke_anything = True
                completed = await self.speaker.speak(sentence, on_level, self._interrupt)
                if not completed:
                    return barge
        finally:
            if watcher:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
