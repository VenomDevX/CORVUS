# ADR-001: Backend language — Python + FastAPI

**Status:** Accepted (2026-07-15)

## Context

Corvus needs a backend process for LLM streaming, persistent memory (SQLite), and — in later milestones — the voice pipeline (Whisper STT, wake word, TTS), desktop automation (PyAutoGUI, Windows UI Automation), browser automation (Playwright), and computer vision. The spec allows either Python + FastAPI or Node.js.

## Decision

Python 3.11 + FastAPI, running as a local service that the Electron app spawns and talks to over localhost HTTP + WebSocket (port 8765).

## Rationale

- The milestone 5–7 stack is overwhelmingly Python-native: `openai-whisper`/`faster-whisper`, `openwakeword`/`pvporcupine`, `pyautogui`, `playwright` (best-supported binding), `opencv`, `pywin32`/`uiautomation`. A Node backend would shell out to Python for most of it anyway.
- FastAPI gives async streaming (WebSocket + SSE) and pydantic schema validation, which the action registry (M6) needs for parameter schemas and risk tiers.
- The frontend/backend seam is a network protocol, so the language split costs little; the typed API client in `frontend/src/lib/api.ts` is the single crossing point.

## Consequences

- Two toolchains (npm + pip/venv); `npm run dev` hides this by launching both.
- Distribution (M9) must bundle a Python runtime (PyInstaller-frozen backend) inside the installer.
- All agent/automation code stays in one language and process space with the LLM loop.
