from __future__ import annotations

import asyncio
import ctypes
import os
import platform
import subprocess
from dataclasses import dataclass

import structlog

from .config import OLLAMA_URL

log = structlog.get_logger("corvus")


@dataclass(frozen=True)
class CatalogModel:
    id: str
    label: str
    download_gb: float
    blurb: str


# Curated Ollama models, smallest to largest. download_gb is the quantized
# weight size; runtime needs roughly that much VRAM (or RAM on CPU) plus
# KV-cache/overhead — see _fit().
MODEL_CATALOG: list[CatalogModel] = [
    CatalogModel("llama3.2:1b", "Llama 3.2 1B", 1.3, "Tiny and fast — fine for quick answers."),
    CatalogModel("qwen2.5-coder:1.5b", "Qwen 2.5 Coder 1.5B", 1.0, "Small coding-focused model."),
    CatalogModel("llama3.2:3b", "Llama 3.2 3B", 2.0, "Great small all-rounder."),
    CatalogModel("phi3.5", "Phi 3.5 Mini", 2.2, "Microsoft's compact reasoning model."),
    CatalogModel("qwen2.5-coder:7b", "Qwen 2.5 Coder 7B", 4.7, "Corvus's default — strong at code and agent tasks."),
    CatalogModel("llama3.1:8b", "Llama 3.1 8B", 4.9, "Strong general assistant."),
    CatalogModel("qwen2.5:14b", "Qwen 2.5 14B", 9.0, "Big and capable — needs serious hardware."),
]

# Weights alone aren't enough: KV cache, activations, and the runtime add up.
_OVERHEAD_GB = 1.5
# CPU inference shares RAM with Windows + apps; keep a healthy reserve.
_RAM_RESERVE_GB = 8.0


def _ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return round(status.ullTotalPhys / (1024**3), 1)


def _gpu() -> dict | None:
    """Name + VRAM of the first NVIDIA GPU, or None (no dGPU / no driver)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        line = out.stdout.strip().splitlines()[0]
        name, vram_mb = (part.strip() for part in line.rsplit(",", 1))
        return {"name": name, "vram_gb": round(float(vram_mb) / 1024, 1)}
    except Exception:
        return None


async def _ollama() -> dict:
    """Is Ollama serving, and which models are already on disk?"""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            models = [
                {"name": m["name"], "size_gb": round(m.get("size", 0) / (1024**3), 1)}
                for m in response.json().get("models", [])
            ]
            return {"running": True, "models": models}
    except Exception:
        return {"running": False, "models": []}


def _fit(model: CatalogModel, ram_gb: float, vram_gb: float | None) -> str:
    needs = model.download_gb + _OVERHEAD_GB
    if vram_gb is not None and vram_gb >= needs:
        return "recommended"
    if ram_gb - _RAM_RESERVE_GB >= needs:
        return "cpu_ok"
    return "too_big"


async def specs() -> dict:
    ram_gb = _ram_gb()
    gpu = await asyncio.to_thread(_gpu)
    vram_gb = gpu["vram_gb"] if gpu else None

    catalog = [
        {
            "id": m.id,
            "label": m.label,
            "download_gb": m.download_gb,
            "blurb": m.blurb,
            "fit": _fit(m, ram_gb, vram_gb),
        }
        for m in MODEL_CATALOG
    ]
    # Best suggestion: the largest model the GPU runs, else the largest that
    # runs acceptably on CPU, else the smallest in the catalog.
    suggested = None
    for tier in ("recommended", "cpu_ok"):
        fitting = [c for c in catalog if c["fit"] == tier]
        if fitting:
            suggested = max(fitting, key=lambda c: c["download_gb"])["id"]
            break
    if suggested is None:
        suggested = min(catalog, key=lambda c: c["download_gb"])["id"]

    return {
        "ram_gb": ram_gb,
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores": os.cpu_count() or 1,
        "gpu": gpu,
        "ollama": await _ollama(),
        "catalog": catalog,
        "suggested": suggested,
    }
