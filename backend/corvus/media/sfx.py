"""Procedural sound-effect synthesis — pure numpy, instant, fully offline.

A prompt is parsed into one or more effect categories; each category is a
parametric DSP generator (shaped noise, oscillators, impulse trains, comb
reverb). Layers are mixed, peak-normalized and returned as 16-bit WAV bytes.
Unknown prompts fall back to the closest texture — synthesis never fails.
"""

from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 44100

# keyword → category. First match wins per word; several categories can layer.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "rain": ("rain", "drizzle", "shower", "storm"),
    "thunder": ("thunder", "lightning", "rumble"),
    "wind": ("wind", "breeze", "gust", "howl"),
    "ocean": ("ocean", "wave", "sea", "surf", "beach"),
    "fire": ("fire", "flame", "campfire", "crackle", "burn"),
    "explosion": ("explosion", "blast", "boom", "bomb", "cannon"),
    "impact": ("impact", "hit", "punch", "thud", "slam", "knock", "drop"),
    "whoosh": ("whoosh", "swoosh", "swish", "sweep", "fly", "dash"),
    "laser": ("laser", "zap", "blaster", "sci-fi", "scifi", "beam"),
    "beep": ("beep", "notification", "alert", "ui", "click", "button", "ping"),
    "footsteps": ("footstep", "footsteps", "walking", "steps", "walk", "run"),
    "heartbeat": ("heartbeat", "heart", "pulse"),
    "bell": ("bell", "chime", "ring", "gong"),
    "birds": ("bird", "birds", "chirp", "tweet", "forest"),
    "static": ("static", "noise", "radio", "glitch"),
    "engine": ("engine", "motor", "car", "machine", "drone"),
    "ambience": ("ambience", "ambient", "room", "atmosphere", "background"),
}


def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def _t(duration: float) -> np.ndarray:
    return np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE


def _lowpass_fast(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """FFT brick-wall lowpass — fast enough for tens of seconds of audio."""
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SAMPLE_RATE)
    spectrum[freqs > cutoff_hz] = 0
    return np.fft.irfft(spectrum, len(x))


def _bandpass(x: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SAMPLE_RATE)
    spectrum[(freqs < low_hz) | (freqs > high_hz)] = 0
    return np.fft.irfft(spectrum, len(x))


def _env_attack_decay(n: int, attack: float, decay: float) -> np.ndarray:
    """Attack/decay envelope; times as fractions of the total length."""
    env = np.ones(n)
    a = max(1, int(n * attack))
    d = max(1, int(n * decay))
    env[:a] = np.linspace(0, 1, a)
    env[-d:] *= np.linspace(1, 0, d)
    return env


def _reverb(x: np.ndarray, decay: float = 0.4, delays_ms=(37, 61, 89)) -> np.ndarray:
    out = x.copy()
    for ms in delays_ms:
        d = int(SAMPLE_RATE * ms / 1000)
        echo = np.zeros_like(x)
        echo[d:] = out[:-d] * decay
        out = out + echo
        decay *= 0.7
    return out


# -- generators ----------------------------------------------------------------


def _gen_rain(t, rng, intensity):
    noise = rng.standard_normal(len(t))
    body = _bandpass(noise, 800, 9000) * 0.5
    # Individual droplet ticks on top of the wash.
    drops = np.zeros(len(t))
    n_drops = int(len(t) / SAMPLE_RATE * 90 * intensity)
    for pos in rng.integers(0, max(1, len(t) - 400), n_drops):
        drops[pos : pos + 400] += _env_attack_decay(400, 0.02, 0.9) * rng.uniform(0.05, 0.25)
    return body + _bandpass(drops * rng.standard_normal(len(t)), 2000, 12000)


def _gen_thunder(t, rng, intensity):
    noise = rng.standard_normal(len(t))
    rumble = _lowpass_fast(noise, 120 + 80 * intensity)
    env = np.exp(-t * (1.2 / max(t[-1], 0.5)))  # long tail
    crack_len = int(0.08 * SAMPLE_RATE)
    crack = np.zeros(len(t))
    if len(t) > crack_len:
        crack[:crack_len] = _bandpass(rng.standard_normal(crack_len), 800, 6000) * np.linspace(1, 0, crack_len)
    return _reverb(rumble * env * 1.4 + crack, decay=0.5)


def _gen_wind(t, rng, intensity):
    noise = rng.standard_normal(len(t))
    # Slowly wandering resonant band = howling gusts.
    slow = np.interp(t, [0, t[-1]], [0, 1])
    gust = 0.5 + 0.5 * np.sin(2 * np.pi * (0.15 + 0.1 * intensity) * t + rng.uniform(0, 6))
    return _bandpass(noise, 150, 900 + 700 * intensity) * (0.35 + 0.65 * gust) * (0.6 + 0.4 * slow)


def _gen_ocean(t, rng, intensity):
    noise = rng.standard_normal(len(t))
    swell = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t + rng.uniform(0, 6))
    return _bandpass(noise, 100, 4000) * (0.25 + 0.75 * swell**2) * (0.6 + 0.4 * intensity)


def _gen_fire(t, rng, intensity):
    base = _bandpass(rng.standard_normal(len(t)), 200, 2500) * 0.3
    crackles = np.zeros(len(t))
    n = int(len(t) / SAMPLE_RATE * 25 * (0.5 + intensity))
    for pos in rng.integers(0, max(1, len(t) - 900), n):
        ln = rng.integers(150, 900)
        crackles[pos : pos + ln] += _env_attack_decay(ln, 0.01, 0.85) * rng.uniform(0.15, 0.5)
    return base + _bandpass(crackles * rng.standard_normal(len(t)), 1500, 9000)


def _gen_explosion(t, rng, intensity):
    noise = rng.standard_normal(len(t))
    env = np.exp(-t * (6 / max(t[-1], 0.3)))
    boom = _lowpass_fast(noise, 200 + 200 * intensity) * env * 2.0
    debris = _bandpass(noise, 1000, 7000) * np.exp(-t * 3) * 0.3
    return _reverb(boom + debris, decay=0.45)


def _gen_impact(t, rng, intensity):
    n = len(t)
    hit_len = min(n, int(0.12 * SAMPLE_RATE))
    x = np.zeros(n)
    hit = _lowpass_fast(rng.standard_normal(hit_len), 400 + 600 * intensity)
    x[:hit_len] = hit * np.exp(-np.linspace(0, 8, hit_len))
    return _reverb(x * 1.6, decay=0.3)


def _gen_whoosh(t, rng, intensity):
    noise = rng.standard_normal(len(t))
    # Band sweeps up then down across the duration.
    sweep = np.sin(np.pi * t / t[-1]) if len(t) else noise
    center = 300 + 2500 * sweep * (0.5 + 0.5 * intensity)
    out = np.zeros(len(t))
    chunk = 2048
    for i in range(0, len(t), chunk):
        c = float(np.mean(center[i : i + chunk]))
        out[i : i + chunk] = _bandpass(noise[i : i + chunk], max(80, c - 250), c + 250)
    return out * np.sin(np.pi * t / t[-1]) * 1.5


def _gen_laser(t, rng, intensity):
    f0, f1 = 2200 + 800 * intensity, 300
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * max(t[-1], 0.05)))
    return np.sin(phase) * np.exp(-t * 10) * 1.2


def _gen_beep(t, rng, intensity):
    freq = 880 * (1 + 0.5 * intensity)
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
    n = len(t)
    env = np.zeros(n)
    beep_len = min(n, int(0.14 * SAMPLE_RATE))
    for start in range(0, n, int(0.3 * SAMPLE_RATE)):
        end = min(start + beep_len, n)
        env[start:end] = _env_attack_decay(end - start, 0.1, 0.3)
        if start + int(0.3 * SAMPLE_RATE) * 2 > n:
            break
    return tone * env * 0.8


def _gen_footsteps(t, rng, intensity):
    x = np.zeros(len(t))
    interval = int(SAMPLE_RATE * (0.55 - 0.2 * intensity))
    step_len = int(0.1 * SAMPLE_RATE)
    for pos in range(0, len(t) - step_len, interval):
        jitter = int(rng.uniform(-0.03, 0.03) * SAMPLE_RATE)
        p = max(0, pos + jitter)
        seg = _lowpass_fast(rng.standard_normal(step_len), 500)
        x[p : p + step_len] += seg * np.exp(-np.linspace(0, 10, step_len)) * rng.uniform(0.7, 1.0)
    return x * 1.4


def _gen_heartbeat(t, rng, intensity):
    x = np.zeros(len(t))
    period = int(SAMPLE_RATE * (0.9 - 0.25 * intensity))
    thump_len = int(0.09 * SAMPLE_RATE)

    def thump(amp):
        tt = np.arange(thump_len) / SAMPLE_RATE
        return np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 30) * amp

    for pos in range(0, len(t) - period, period):
        for offset, amp in ((0, 1.0), (int(0.18 * SAMPLE_RATE), 0.6)):
            p = pos + offset
            if p + thump_len < len(t):
                x[p : p + thump_len] += thump(amp)
    return x * 1.6


def _gen_bell(t, rng, intensity):
    f = 520 + 300 * intensity
    partials = [(1.0, 1.0), (2.76, 0.5), (5.4, 0.25), (8.9, 0.12)]
    x = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * (1.2 + m)) for m, a in partials)
    return _reverb(x, decay=0.35)


def _gen_birds(t, rng, intensity):
    x = np.zeros(len(t))
    n_chirps = int(len(t) / SAMPLE_RATE * (2 + 3 * intensity))
    for _ in range(n_chirps):
        ln = int(rng.uniform(0.08, 0.25) * SAMPLE_RATE)
        pos = rng.integers(0, max(1, len(t) - ln))
        tt = np.arange(ln) / SAMPLE_RATE
        f = rng.uniform(2000, 4500)
        warble = f + rng.uniform(200, 900) * np.sin(2 * np.pi * rng.uniform(8, 20) * tt)
        x[pos : pos + ln] += np.sin(2 * np.pi * np.cumsum(warble) / SAMPLE_RATE) * _env_attack_decay(ln, 0.2, 0.3) * 0.3
    return x


def _gen_static(t, rng, intensity):
    x = rng.standard_normal(len(t)) * 0.5
    # Glitchy dropouts.
    for _ in range(int(4 * intensity) + 1):
        ln = int(rng.uniform(0.02, 0.1) * SAMPLE_RATE)
        pos = rng.integers(0, max(1, len(t) - ln))
        x[pos : pos + ln] *= rng.uniform(0, 0.2)
    return x


def _gen_engine(t, rng, intensity):
    f = 60 + 80 * intensity
    wobble = 1 + 0.03 * np.sin(2 * np.pi * 3 * t)
    tone = np.sign(np.sin(2 * np.pi * f * wobble * t)) * 0.4  # square-ish
    return _lowpass_fast(tone + rng.standard_normal(len(t)) * 0.08, 900)


def _gen_ambience(t, rng, intensity):
    return _bandpass(rng.standard_normal(len(t)), 80, 1200) * (0.25 + 0.2 * intensity)


_GENERATORS = {
    "rain": _gen_rain,
    "thunder": _gen_thunder,
    "wind": _gen_wind,
    "ocean": _gen_ocean,
    "fire": _gen_fire,
    "explosion": _gen_explosion,
    "impact": _gen_impact,
    "whoosh": _gen_whoosh,
    "laser": _gen_laser,
    "beep": _gen_beep,
    "footsteps": _gen_footsteps,
    "heartbeat": _gen_heartbeat,
    "bell": _gen_bell,
    "birds": _gen_birds,
    "static": _gen_static,
    "engine": _gen_engine,
    "ambience": _gen_ambience,
}


def categories_for(prompt: str) -> list[str]:
    words = prompt.lower()
    matched = [cat for cat, keys in _KEYWORDS.items() if any(k in words for k in keys)]
    return matched[:3] or ["ambience"]


def synthesize_sfx(
    prompt: str,
    duration: float = 3.0,
    intensity: float = 0.6,
    seed: int | None = None,
) -> tuple[bytes, list[str]]:
    """Render the prompt to WAV bytes; returns (wav, categories used)."""
    duration = float(min(max(duration, 0.5), 15.0))
    intensity = float(min(max(intensity, 0.0), 1.0))
    rng = _rng(seed)
    t = _t(duration)
    cats = categories_for(prompt)

    mix = np.zeros(len(t))
    for cat in cats:
        mix = mix + _GENERATORS[cat](t, rng, intensity)

    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * (0.55 + 0.4 * intensity)
    # Gentle edges so clips never click.
    mix *= _env_attack_decay(len(mix), 0.01, 0.02)
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue(), cats


__all__ = ["synthesize_sfx", "categories_for", "SAMPLE_RATE"]
