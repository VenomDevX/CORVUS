"""Corvus backend configuration: paths, network, and model defaults.

Environment overrides (CORVUS_*) exist so tests and dev setups can redirect
state without touching the user's real data directory.
"""

import os
from pathlib import Path

# Limit CPU thread pools for OpenBLAS / OpenMP / MKL to prevent RAM bloat
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")

HOST = os.environ.get("CORVUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("CORVUS_PORT", "8765"))

OLLAMA_URL = os.environ.get("CORVUS_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("CORVUS_DEFAULT_MODEL", "qwen2.5-coder:latest")
DEFAULT_NUM_CTX = int(os.environ.get("CORVUS_NUM_CTX", "4096"))



def data_dir() -> Path:
    override = os.environ.get("CORVUS_DATA_DIR")
    if override:
        path = Path(override)
    else:
        path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Corvus"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "corvus.db"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return log_dir() / "corvus.log"


SYSTEM_PROMPT = """You are Corvus, a Windows desktop AI assistant.

Personality: friendly and professional; occasionally funny when it fits, never
annoying, never overly verbose. Prefer short, direct answers with Markdown
formatting (code blocks with language tags, tables where they help).

When you take or prepare an action, always say what you are doing or just did
("Opening Chrome…", "Deleted 3 files from Downloads.") - never act silently."""
