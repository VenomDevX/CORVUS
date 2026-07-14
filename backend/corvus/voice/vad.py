"""Energy-based voice activity detection and utterance segmentation.

Frame-level: adaptive noise floor (EMA over non-speech frames) with a ratio
threshold. Utterance-level: a small state machine that opens on sustained
speech and closes after a silence tail or a hard cap.

Deliberately dependency-light; the interface (is_speech per frame, Segmenter
events) is what matters — a neural VAD can replace the energy heuristic later
without touching the pipeline.
"""

from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000


def rms(frame: np.ndarray) -> float:
    """Root-mean-square level of a float32 [-1, 1] frame."""
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))


@dataclass
class EnergyVAD:
    """Adaptive threshold: speech when rms exceeds noise_floor * ratio."""

    ratio: float = 3.5
    min_level: float = 0.010
    floor: float = 0.005
    floor_alpha: float = 0.05

    def is_speech(self, frame: np.ndarray) -> bool:
        level = rms(frame)
        speech = level > max(self.min_level, self.floor * self.ratio)
        if not speech:
            self.floor = (1 - self.floor_alpha) * self.floor + self.floor_alpha * level
        return speech


@dataclass
class Segmenter:
    """Collects frames into one utterance.

    feed() returns "open" when the utterance starts, "close" when it ends
    (silence tail elapsed or max length hit), else None. The captured audio
    is in `audio()` after close.
    """

    vad: EnergyVAD = field(default_factory=EnergyVAD)
    open_frames: int = 3          # consecutive speech frames to open (~90 ms)
    tail_ms: int = 800            # silence to close
    max_ms: int = 30000           # hard utterance cap
    preroll_frames: int = 8       # audio kept from before the opening frame

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._preroll: list[np.ndarray] = []
        self._frames: list[np.ndarray] = []
        self._speech_run = 0
        self._silence_run = 0
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    def feed(self, frame: np.ndarray) -> str | None:
        speech = self.vad.is_speech(frame)

        if not self._is_open:
            self._preroll.append(frame)
            if len(self._preroll) > self.preroll_frames:
                self._preroll.pop(0)
            self._speech_run = self._speech_run + 1 if speech else 0
            if self._speech_run >= self.open_frames:
                self._is_open = True
                self._frames = list(self._preroll)
                self._silence_run = 0
                return "open"
            return None

        self._frames.append(frame)
        self._silence_run = 0 if speech else self._silence_run + 1
        if self._silence_run * FRAME_MS >= self.tail_ms:
            self._is_open = False
            return "close"
        if len(self._frames) * FRAME_MS >= self.max_ms:
            self._is_open = False
            return "close"
        return None

    def audio(self) -> np.ndarray:
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames).astype(np.float32)
