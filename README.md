# Corvus

Corvus is a Windows desktop AI assistant — an animated, voice-ready companion that lives in your taskbar, remembers what matters, and (in later milestones) acts on your behalf across the OS and the web.

**Current state (Milestones 1–4):** Electron shell with the Corvus orb and Fluent dark/light theming, streaming text chat against local [Ollama](https://ollama.com), persistent conversation history and inspectable memory in SQLite, structured logging.

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

## Other commands

```powershell
npm run guard    # naming lint (product name must be Corvus everywhere)
npm test         # guard + frontend vitest + backend pytest
npm run assets   # re-export logo SVGs to ICO/PNG (design/exports)
```

## Layout

See `CLAUDE.md` for the project rules, design-token contract, and milestone roadmap. Architecture decisions live in `docs/adr/`.

Powered by Corvus.
