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

Done: **all milestones M1–M9 complete.** M1 scaffold, M2 design system, M3 shell, M4 chat+memory, M5 voice pipeline, M6 agent action registry + confirmations, M7 browser automation + computer vision, M8 multi-provider LLM + plugins + workflows + notifications, M9 installer + auto-update + crash recovery + logging hardening. Section 15 of the product spec (avatars, phone app, home automation) remains out of scope. Future work is refinement within the existing architecture, not new milestones.

M9: crash recovery + session restore in `backend/corvus/session.py` (unclean-shutdown detection, active-conversation restore); rotating logs (`log.py`); auto-update via `frontend/electron/updater.ts` (electron-updater); installer config in `frontend/electron-builder.yml` (NSIS) + `installer/corvus-backend.spec` (PyInstaller freeze); `npm run dist` builds it. The final NSIS packaging step needs Windows Developer Mode on this machine (winCodeSign symlink extraction).

M8 subsystems: multi-provider LLM in `backend/corvus/llm/` (`factory.py` ProviderManager + openai_compat/anthropic/gemini providers; API keys encrypted via `vault.py` DPAPI); notifications/reminders in `backend/corvus/notifications/`; workflows in `backend/corvus/workflows/` (ordered action sequences, no high-risk steps); plugin SDK in `backend/corvus/plugins/` (manifest.json + plugin.py, permission-gated). Plugins/workflows/notifications register their actions into the shared registry via `build_default_registry` kwargs and app wiring.

Actions (M6) live in `backend/corvus/actions/`: every OS capability is a registered `ActionSpec` with a risk tier (`safe`/`low`/`medium`/`high`) and, for anything that confirms, a `confirm_prompt` that states the exact consequence. Adding a capability = write a handler, register a spec — never a new if/else branch in the agent loop. `medium`/`high` always route through the user; voice mode (M5) deliberately stays text-chat-only for actions, since confirmations need the visible card.

Browser automation + computer vision (M7) live in `backend/corvus/automation/` (`browser.py` = Playwright Chromium engine, `vision.py` = rapidocr OCR + optional vision-model); their actions are registered from `actions/browser_handlers.py` and only when a browser engine + provider are supplied to `build_default_registry`. Web element targeting uses Playwright locators; native-window targeting uses screenshot OCR + PyAutoGUI. Corvus never types stored passwords — `browser_open_login` hands off to the browser's credential manager after per-site confirmation.

Environment note: this machine runs a **Microsoft Store Python**, which filesystem-virtualizes `%LOCALAPPDATA%`. A file an external process (e.g. PowerShell) writes there isn't visible to the backend at the same path — keep file capture in-process (screenshots use Pillow `ImageGrab`, not a PowerShell shell-out).

Build note: `dist:backend` pins `OPENBLAS_NUM_THREADS`/`OMP_NUM_THREADS`/`MKL_NUM_THREADS` to 1. Without them, PyInstaller's isolated `collect_all(faster_whisper)` subprocess loads OpenBLAS at full thread count and dies with "Memory allocation still failed after 10 retries" on this machine. Keep the caps.

Only one Corvus may run at a time (Electron single-instance lock, `main.ts`). A second launch — dev while the packaged app is open, or vice versa — quits instantly with exit code 0 instead of erroring. A running `Corvus.exe` also locks `dist-installer/win-unpacked/`, which fails the packaging step with "Access is denied"; close the app before `npm run dist`.

## Quality bar

No TODO comments in shipped code — deferred work goes in the milestone list above. Destructive/high-risk agent actions (M6+) always require explicit, specific confirmation. API keys go through Windows credential vault/DPAPI, never plaintext. Run `npm run guard && npm test` before committing.
