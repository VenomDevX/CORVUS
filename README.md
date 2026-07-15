# Corvus

Corvus is a Windows desktop AI assistant — an animated, voice-ready companion that lives in your taskbar, remembers what matters, and (in later milestones) acts on your behalf across the OS and the web.

**Current state (Milestones 1–8):** Electron shell with the Corvus orb and Fluent dark/light theming; streaming chat across **multiple LLM providers** (local Ollama plus OpenAI, Anthropic, Gemini, DeepSeek, with API keys encrypted via Windows DPAPI); persistent history and inspectable memory in SQLite; a full voice pipeline (local "Hey Corvus" wake word + Whisper STT + streamed neural TTS with barge-in); an agent that controls Windows through a permissioned action registry with exact-consequence confirmations; browser automation + computer vision (Playwright navigation/research, OCR screenshot understanding and on-screen clicking); native **notifications, timers, and reminders**; user-definable **workflows** (manual/scheduled/voice triggers); and a **plugin SDK** with a marketplace and per-plugin permissions. Whisper (~220 MB), the OCR model, and Chromium download on first use.

## Prerequisites

- Windows 11, Node.js ≥ 20, Python 3.11
- Ollama installed and running (`ollama serve`) with at least one model pulled (default: `qwen2.5-coder:latest`)

## Setup

```powershell
npm install
npm install --prefix frontend
cd backend; python -m venv .venv; .venv\Scripts\pip install -e .[dev]; cd ..
```

## Run

```powershell
npm run dev      # starts the FastAPI backend, Vite, and Electron together
```

### Troubleshooting

If Electron fails to start with a missing-binary error, its postinstall step
downloaded the zip but failed to extract it silently. Fix:

```powershell
cd frontend
Expand-Archive -Force "$env:LOCALAPPDATA\electron\Cache\<hash>\electron-v*-win32-x64.zip" node_modules\electron\dist
Set-Content node_modules\electron\path.txt "electron.exe" -NoNewline -Encoding ascii
```

## Other commands

```powershell
npm run guard    # naming lint (product name must be Corvus everywhere)
npm test         # guard + frontend vitest + backend pytest
npm run assets   # re-export logo SVGs to ICO/PNG (design/exports)
```

## Layout

See `CLAUDE.md` for the project rules, design-token contract, and milestone roadmap. Architecture decisions live in `docs/adr/`.

Powered by Corvus.
