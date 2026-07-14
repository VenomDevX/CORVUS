import asyncio
import threading

import numpy as np
import pytest

from corvus.voice.pipeline import VoicePipeline
from corvus.voice.tts import SentenceChunker, prosody_for, _strip_markdown
from corvus.voice.vad import FRAME_SAMPLES, EnergyVAD, Segmenter
from corvus.voice.wake import matches_wake_phrase
from tests.conftest import FakeProvider


def silence(n=1):
    return [np.zeros(FRAME_SAMPLES, dtype=np.float32) for _ in range(n)]


def speech(n=1, amp=0.2):
    rng = np.random.default_rng(42)
    return [
        (amp * rng.standard_normal(FRAME_SAMPLES)).astype(np.float32).clip(-1, 1)
        for _ in range(n)
    ]


# -- VAD / segmentation -------------------------------------------------------

def test_vad_distinguishes_speech_from_silence():
    vad = EnergyVAD()
    assert not any(vad.is_speech(f) for f in silence(5))
    assert all(vad.is_speech(f) for f in speech(5))


def test_segmenter_opens_and_closes_on_silence_tail():
    seg = Segmenter()
    events = [seg.feed(f) for f in silence(5) + speech(10) + silence(40)]
    assert "open" in events
    assert "close" in events
    assert seg.audio().size > 0
    # Preroll means captured audio starts before the opening frame.
    assert seg.audio().size >= 10 * FRAME_SAMPLES


def test_segmenter_respects_max_length():
    seg = Segmenter(max_ms=300)
    closed = False
    for f in speech(30):
        if seg.feed(f) == "close":
            closed = True
            break
    assert closed


# -- wake matching -------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hey Corvus", True),
        ("corvus, what time is it", True),
        ("Hey, Corpus!", True),  # common whisper mishearing
        ("core vus wake up", True),
        ("what a lovely morning", False),
        ("crocus flowers", False),
    ],
)
def test_wake_phrase_matching(text, expected):
    assert matches_wake_phrase(text) is expected


# -- TTS chunking / prosody -----------------------------------------------------

def test_sentence_chunker_streams_sentences():
    chunker = SentenceChunker()
    out = []
    for delta in ["Hel", "lo there. How ", "are you? I", "'m fine!"]:
        out.extend(chunker.feed(delta))
    tail = chunker.flush()
    assert out == ["Hello there.", "How are you?"]
    assert tail == "I'm fine!"


def test_sentence_chunker_glues_short_fragments():
    chunker = SentenceChunker()
    out = chunker.feed("This is a full sentence. Ok. And another full one here.")
    assert out[0] == "This is a full sentence. Ok."


def test_prosody_hints():
    assert prosody_for("Amazing!") == ("+8%", "+12Hz")
    assert prosody_for("Really?")[1] == "+18Hz"
    assert prosody_for("Fine.") == ("+0%", "+0Hz")


def test_strip_markdown_for_speech():
    text = "Use `npm run dev` — see [docs](https://x.dev).\n```python\nprint(1)\n```"
    clean = _strip_markdown(text)
    assert "`" not in clean and "http" not in clean
    assert "npm run dev" in clean
    assert "code block omitted" in clean


# -- pipeline (all hardware faked) ----------------------------------------------

class FakeMic:
    def __init__(self):
        self.on_frame = None

    def start(self, on_frame):
        self.on_frame = on_frame

    def stop(self):
        self.on_frame = None


class FakeTranscriber:
    def __init__(self, text="hello corvus what is two plus two"):
        self.text = text

    async def transcribe(self, audio, language=None):
        return self.text if audio.size else ""


class FakeSpeaker:
    def __init__(self):
        self.spoken: list[str] = []
        self.voice = "fake-voice"

    async def speak(self, text, on_level, interrupt: threading.Event) -> bool:
        if interrupt.is_set():
            return False
        self.spoken.append(text)
        on_level(0.4)
        return True


class FakeWake:
    def __init__(self, result=True):
        self.result = result

    async def detect(self, audio) -> bool:
        return self.result


async def _drain(q: asyncio.Queue) -> list[dict]:
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


@pytest.fixture
def pipeline(repo):
    provider = FakeProvider(chunks=["Two plus two ", "is four. ", "Easy!"])
    repo.set_setting("model", "fake")
    p = VoicePipeline(
        repo,
        provider,
        mic=FakeMic(),
        transcriber=FakeTranscriber(),
        speaker=FakeSpeaker(),
        wake=FakeWake(),
    )
    return p


async def test_ptt_full_turn(pipeline):
    await pipeline.start()
    assert pipeline.available
    events_q = pipeline.subscribe()

    pipeline.push_to_talk()
    await asyncio.sleep(0.05)
    # Simulate the user speaking, then going quiet.
    for f in speech(10) + silence(40):
        pipeline._push_frame(f)

    for _ in range(100):
        await asyncio.sleep(0.05)
        if pipeline.state == "idle" and not pipeline._frames.qsize():
            events = await _drain(events_q)
            if any(e["type"] == "assistant_done" for e in events):
                break
    else:
        pytest.fail("voice turn did not complete")

    types = [e["type"] for e in events]
    assert "transcript" in types
    assert "assistant_delta" in types
    assert pipeline.speaker.spoken  # sentences were spoken
    assert pipeline.speaker.spoken[0].startswith("Two plus two")

    # Turn persisted to the conversation store.
    convs = pipeline.repo.list_conversations()
    assert len(convs) == 1
    messages = pipeline.repo.list_messages(convs[0]["id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]
    await pipeline.stop()


async def test_wake_toggle_persists(pipeline):
    await pipeline.start()
    pipeline.set_wake_enabled(False)
    assert pipeline.repo.get_setting("wake_enabled") == "false"
    pipeline.set_wake_enabled(True)
    assert pipeline.repo.get_setting("wake_enabled") == "true"
    await pipeline.stop()


async def test_stop_speaking_interrupts(pipeline):
    await pipeline.start()
    pipeline.stop_speaking()
    assert pipeline._interrupt.is_set()
    await pipeline.stop()
