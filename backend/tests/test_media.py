import io
import wave

import numpy as np
import pytest
from PIL import Image

from corvus.media.profiles import profile_for
from corvus.media.sfx import categories_for, synthesize_sfx
from corvus.media.store import MediaStore
from corvus.media.video import VideoEngine


# -- profiles -------------------------------------------------------------------


def test_profile_tiers():
    low = profile_for(8.0, None, cpu_cores=4)
    mid = profile_for(16.0, None, cpu_cores=8)
    high = profile_for(32.0, 12.0, cpu_cores=16)
    assert low["tier"] == "low" and low["image_max_size"] == 384
    assert low["unload_after_generate"] is True
    assert mid["tier"] == "mid" and mid["image_max_size"] == 512
    assert mid["unload_after_generate"] is False
    assert high["tier"] == "high" and high["image_max_size"] == 768
    assert 768 in high["image_sizes"] and 768 not in low["image_sizes"]
    assert low["intra_op_threads"] == 2
    assert "CPUExecutionProvider" in low["ort_providers"]


# -- sfx --------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt", ["heavy rain and thunder", "laser zap", "footsteps in a hall", "xyzzy blorp"]
)
def test_sfx_returns_valid_wav(prompt):
    wav, cats = synthesize_sfx(prompt, duration=1.0, intensity=0.5, seed=42)
    assert cats
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == 44100
        assert w.getnchannels() == 1
        assert w.getnframes() == 44100


def test_sfx_category_parsing():
    assert "rain" in categories_for("gentle RAIN on a roof")
    assert "thunder" in categories_for("rain with thunder")
    assert categories_for("complete gibberish qqq") == ["ambience"]


def test_sfx_duration_clamped():
    wav, _ = synthesize_sfx("beep", duration=1000, seed=1)
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getnframes() / w.getframerate() <= 15.01


def test_sfx_deterministic_with_seed():
    a, _ = synthesize_sfx("wind", duration=0.6, seed=7)
    b, _ = synthesize_sfx("wind", duration=0.6, seed=7)
    assert a == b


# -- store -------------------------------------------------------------------


def test_store_roundtrip(tmp_path):
    store = MediaStore(tmp_path / "media.db")
    row = store.add("sfx", "test beep", {"duration": 1}, b"RIFFxxxx")
    assert row["kind"] == "sfx" and row["params"]["duration"] == 1
    assert store.file_path(row["id"]).read_bytes() == b"RIFFxxxx"
    assert [r["id"] for r in store.list("sfx")] == [row["id"]]
    assert store.list("image") == []
    assert store.delete(row["id"]) is True
    assert store.file_path(row["id"]) is None
    assert store.delete(row["id"]) is False
    store.close()


def test_store_rejects_bad_kind(tmp_path):
    store = MediaStore(tmp_path / "media.db")
    with pytest.raises(ValueError):
        store.add("script", "x", {}, b"")
    store.close()


# -- video (image engine stubbed) ---------------------------------------------


class _StubImageEngine:
    def generate(self, model_id, prompt, size=384, seed=None, progress=None, **_):
        rng = np.random.default_rng(seed)
        color = tuple(int(c) for c in rng.integers(0, 255, 3))
        img = Image.new("RGB", (size, size), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def test_video_produces_multiframe_gif():
    profile = profile_for(16.0, None, cpu_cores=8)
    engine = VideoEngine(_StubImageEngine(), profile)
    ticks: list[float] = []
    clip = engine.generate("sd-turbo", "a city at night", seconds=2.0, seed=3,
                           progress=ticks.append)
    img = Image.open(io.BytesIO(clip))
    assert img.format == "GIF"
    img.seek(1)  # a second frame must exist
    assert ticks and ticks[-1] == pytest.approx(1.0)


def test_video_clamps_duration():
    profile = profile_for(8.0, None, cpu_cores=4)
    engine = VideoEngine(_StubImageEngine(), profile)
    clip = engine.generate("sd-turbo", "x", seconds=9999, seed=1)
    frames = 0
    img = Image.open(io.BytesIO(clip))
    try:
        while True:
            img.seek(frames)
            frames += 1
    except EOFError:
        pass
    assert frames <= 10 * profile["video_fps"] + 5
