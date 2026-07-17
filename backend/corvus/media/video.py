"""Local motion clips: SD keyframes + smooth interpolation, assembled with
Pillow into an animated clip. Real video output on any device — frame count
and resolution adapt to the machine's profile. (Full text-to-video models do
not run on consumer hardware; this is the honest local implementation.)"""

from __future__ import annotations

import io
from typing import Callable

import structlog
from PIL import Image

log = structlog.get_logger("corvus")


def _ken_burns(frame: Image.Image, zoom: float) -> Image.Image:
    """Slow zoom-in crop: motion inside a single keyframe."""
    w, h = frame.size
    crop = 1 / zoom
    cw, ch = int(w * crop), int(h * crop)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return frame.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.LANCZOS)


class VideoEngine:
    def __init__(self, image_engine, profile: dict):
        self.images = image_engine
        self.profile = profile

    def generate(
        self,
        model_id: str,
        prompt: str,
        seconds: float = 4.0,
        motion: str = "zoom",
        size: int = 384,
        seed: int | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> bytes:
        seconds = float(min(max(seconds, 2.0), 10.0))
        fps = int(self.profile["video_fps"])
        keyframe_count = int(self.profile["video_max_keyframes"])
        size = int(min(size, self.profile["image_max_size"], 512))
        total_frames = int(seconds * fps)

        # 1) Keyframes: same prompt, different seeds → related scenes.
        keyframes: list[Image.Image] = []
        base_seed = seed if seed is not None else 0
        for k in range(keyframe_count):
            png = self.images.generate(
                model_id,
                prompt,
                size=size,
                seed=base_seed + k * 7919,
                progress=None,
            )
            keyframes.append(Image.open(io.BytesIO(png)).convert("RGB"))
            if progress:
                progress(0.8 * (k + 1) / keyframe_count)

        # 2) Interpolate: crossfade between keyframes with gentle Ken Burns zoom.
        frames: list[Image.Image] = []
        segments = max(1, len(keyframes) - 1) if len(keyframes) > 1 else 1
        per_segment = max(2, total_frames // segments)
        for s in range(segments):
            a = keyframes[s]
            b = keyframes[min(s + 1, len(keyframes) - 1)]
            for f in range(per_segment):
                t = f / per_segment
                zoom = 1.0 + 0.08 * (s + t) / segments if motion == "zoom" else 1.0
                fa = _ken_burns(a, zoom)
                if a is b:
                    frames.append(fa)
                else:
                    fb = _ken_burns(b, zoom)
                    # Bias the crossfade so keyframes hold before blending.
                    blend = min(1.0, max(0.0, (t - 0.35) / 0.65)) if t > 0.35 else 0.0
                    frames.append(Image.blend(fa, fb, blend))
            if progress:
                progress(0.8 + 0.2 * (s + 1) / segments)

        buf = io.BytesIO()
        frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0,
        )
        log.info("video_generated", frames=len(frames), keyframes=keyframe_count, size=size)
        return buf.getvalue()
