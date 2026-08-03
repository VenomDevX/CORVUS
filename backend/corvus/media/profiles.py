"""Device-adaptive quality profiles for local media generation.

Every device gets a working configuration; better hardware gets bigger
outputs. The rules keep memory bounded: capped ONNX threads, one heavy job at
a time (enforced by the shared job lock in the API layer), and on low-RAM
machines the model is unloaded after each generation.
"""

from __future__ import annotations

import os


def _ort_providers() -> list[str]:
    """DirectML accelerates on any DX12 GPU when the package is present;
    plain CPU otherwise — both paths work on every Windows machine."""
    try:
        import onnxruntime

        available = onnxruntime.get_available_providers()
    except Exception:
        return ["CPUExecutionProvider"]
    providers = []
    if "DmlExecutionProvider" in available:
        providers.append("DmlExecutionProvider")
    providers.append("CPUExecutionProvider")
    return providers


def profile_for(ram_gb: float, vram_gb: float | None, cpu_cores: int | None = None) -> dict:
    cores = cpu_cores or os.cpu_count() or 4
    providers = _ort_providers()
    gpu = "DmlExecutionProvider" in providers

    if ram_gb >= 24 or (vram_gb or 0) >= 8:
        tier = "high"
        max_size, steps, video_frames = 768, 6, 4
    elif ram_gb >= 12:
        tier = "mid"
        max_size, steps, video_frames = 512, 4, 3
    else:
        tier = "low"
        max_size, steps, video_frames = 384, 3, 2

    return {
        "tier": tier,
        "ram_gb": ram_gb,
        "image_max_size": max_size,
        "image_sizes": [s for s in (384, 512, 768) if s <= max_size],
        "image_steps": steps,
        "ort_providers": providers,
        "gpu_accelerated": gpu,
        "intra_op_threads": min(4, max(1, cores - 2)),
        "unload_after_generate": ram_gb < 12,
        "video_max_keyframes": video_frames,
        "video_fps": 12 if tier == "high" else 10,
        "sfx_sample_rate": 44100,
    }
