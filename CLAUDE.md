# Corvus — Project Rules

Corvus is a Windows desktop AI assistant: Electron + React frontend, Python + FastAPI backend, local-first (Ollama, SQLite).

## Naming rule (non-negotiable)

The product name is **Corvus** — in every string, file name, package name, window title, tray tooltip, log header, doc, and installer field. The old placeholder project name (spelled out only in `scripts/naming-guard.mjs`) must never appear anywhere. Enforced by `npm run guard` (`scripts/naming-guard.mjs`), which runs in pre-commit and must stay wired in. Wake word (Milestone 5): "Hey Corvus" / "Corvus".

## Stack (decided — do not re-litigate)

- **Frontend:** Electron + React + TypeScript + Vite, Tailwind CSS, Framer Motion, Fluent UI (`@fluentui/react-components`) as base layer. Dark theme is default.
- **Backend:** Python 3.11 + FastAPI (see `docs/adr/001-backend-python-fastapi.md`). Electron spawns it; they talk over localhost HTTP + WebSocket (default port 8765).
- **LLM:** all providers implement the `LLMProvider` protocol in `backend/corvus/llm/base.py`. Current provider: local Ollama (`qwen2.5-coder:latest` default).
- **Data:** SQLite at `%LOCALAPPDATA%\Corvus\corvus.db`; logs at `%LOCALAPPDATA%\Corvus\logs\corvus.log` (JSON lines).

## Design tokens

`design/tokens.json` is the single source of truth for colors, type scale, spacing, radii, shadows, and motion. Tailwind theme is generated from it (`frontend/tailwind.config.ts` imports it) — never hardcode hex values or px sizes in components. Key tokens: bg deep-black `#05060A`, midnight-blue `#0B1220`, accent electric-blue `#4F8CFF`, default radius 8px, 4px spacing grid, fonts Inter (UI) / JetBrains Mono (code).

Brand assets are code-first: SVGs in `design/logo/`, exported to ICO/PNG via `npm run assets` (`scripts/export-assets.mjs`). Figma sync is deferred; when it happens it derives from `tokens.json`, not the other way around.

## Layout

```
frontend/    Electron + React app (electron/ = main process, src/ = renderer)
backend/     FastAPI app (corvus/ package, tests/)
design/      tokens.json, logo SVGs, exported assets
scripts/     naming-guard.mjs, export-assets.mjs
automation/  reserved for Milestone 6+ (action registry, PyAutoGUI, Playwright)
installer/   reserved for Milestone 9 — do not touch
docs/adr/    architecture decision records
```

## Milestones / don't-touch list

Done: M1 scaffold, M2 design system, M3 shell, M4 chat+memory, M5 voice pipeline, M6 agent action registry + confirmations. Not yet built — do not stub or partially implement outside their milestone: browser automation/CV (M7), multi-provider switching, plugins, workflows, notifications (M8), installer/auto-update (M9). Section 15 of the product spec (avatars, phone app, home automation) is out of scope entirely.

Actions (M6) live in `backend/corvus/actions/`: every OS capability is a registered `ActionSpec` with a risk tier (`safe`/`low`/`medium`/`high`) and, for anything that confirms, a `confirm_prompt` that states the exact consequence. Adding a capability = write a handler, register a spec — never a new if/else branch in the agent loop. `medium`/`high` always route through the user; voice mode (M5) deliberately stays text-chat-only for actions, since confirmations need the visible card.

## Quality bar

No TODO comments in shipped code — deferred work goes in the milestone list above. Destructive/high-risk agent actions (M6+) always require explicit, specific confirmation. API keys go through Windows credential vault/DPAPI, never plaintext. Run `npm run guard && npm test` before committing.
