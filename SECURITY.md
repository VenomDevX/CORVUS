# Corvus Security

Corvus is local-first: the LLM (Ollama), conversation history, memories, and logs all live on the user's machine. The FastAPI backend binds to `127.0.0.1` only and is never exposed to the network. This document tracks the security posture: what is already enforced, and the hardening roadmap with live status.

## Reporting a vulnerability

Open a private security advisory on GitHub (Security → Advisories → Report a vulnerability) rather than a public issue.

## Already enforced

- Backend binds loopback only (`127.0.0.1:8765`); nothing listens on external interfaces.
- API keys for optional cloud providers are encrypted with Windows DPAPI (user-scoped) and stored base64 in SQLite — never plaintext on disk (verified by scanning the raw DB file).
- Agent actions are risk-tiered (`safe`/`low`/`medium`/`high`); `medium`/`high` always require explicit user confirmation stating the exact consequence. Voice mode cannot trigger actions (confirmations need the visible card).
- Corvus never types stored passwords — login flows hand off to the browser's own credential manager after per-site consent.
- Electron renderer is locked down: `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, minimal typed IPC bridge.
- `openPath` IPC blocks executable extensions (`.exe`, `.bat`, `.ps1`, …); `openExternal` only accepts `http(s)` URLs.
- Single-instance lock prevents a second Corvus from racing the first.

## Hardening roadmap

Status legend: ✅ done · 🔲 pending

| # | Priority | Item | Status |
|---|----------|------|--------|
| 1 | **P1** | **Backend API authentication** — Electron generates a random token per launch, passes it to the spawned backend, and every HTTP request and WebSocket handshake must present it. Blocks any other local process from reading conversations or driving the agent. `/health` stays open for liveness checks. | 🔲 pending |
| 2 | **P1** | **Auto-update feed hijack** — `electron-builder.yml` pointed at `updates.corvus.app`, a placeholder domain nobody owns; whoever registers it could serve malicious "updates". Point the feed at this repo's GitHub Releases instead. | 🔲 pending |
| 3 | P2 | **Code-sign the installer** — unsigned builds trigger SmartScreen and give the updater no signature to verify. Requires a paid certificate (OV/EV or Azure Trusted Signing); until then updates are notify-only in spirit. | 🔲 pending (needs certificate purchase) |
| 4 | P2 | **Plugin trust model** — plugins are Python loaded in-process; manifest permissions gate registry actions but not arbitrary code. Add first-run consent showing permissions + a content hash of `plugin.py`, re-prompt on hash change. Full process sandboxing deferred until a marketplace exists. | 🔲 pending |
| 5 | P2 | **Prompt-injection hardening** — web page text and OCR output fed to the model can carry hostile instructions. Keep risk-tier confirmations non-negotiable; wrap web/OCR content in delimiters the system prompt declares to be untrusted data, not instructions. | 🔲 pending |
| 6 | P3 | **Electron navigation guards** — add `will-navigate` deny + `setWindowOpenHandler` (open external links via the shell, never in-app). Defense in depth; the renderer only loads local content today. | 🔲 pending |
| 7 | P3 | **Tighten CORS** — drop the dev-server origins (`localhost:5173`) in packaged builds; largely moot once item 1 lands. | 🔲 pending |
| 8 | P3 | **Data at rest** — conversations/memories are plaintext SQLite; audit `log.py` so message bodies never reach logs; consider SQLCipher or DPAPI-wrapping message content if secrets are expected in chats. | 🔲 pending |
| 9 | P3 | **Upload endpoint hardening** — enforce filename sanitization (no traversal) and a size cap on `/upload`. | 🔲 pending |
| 10 | P3 | **Supply chain** — enable Dependabot on the repo; add `npm audit` / `pip-audit` alongside the naming guard in CI/pre-commit. | 🔲 pending |

Items are checked off in this file in the same commit that implements them.
