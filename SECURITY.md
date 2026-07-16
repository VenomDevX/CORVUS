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
| 1 | **P1** | **Backend API authentication** — Electron generates a random token per launch, passes it to the spawned backend, and every HTTP request and WebSocket handshake must present it. Blocks any other local process from reading conversations or driving the agent. `/health` stays open for liveness checks. | ✅ done |
| 2 | **P1** | **Auto-update feed hijack** — `electron-builder.yml` pointed at `updates.corvus.app`, a placeholder domain nobody owns; whoever registers it could serve malicious "updates". Point the feed at this repo's GitHub Releases instead. | ✅ done |
| 3 | P2 | **Code-sign the installer** — unsigned builds trigger SmartScreen and give the updater no signature to verify. Requires a paid certificate (OV/EV or Azure Trusted Signing); until then updates are notify-only in spirit. | 🔲 pending (needs certificate purchase) |
| 4 | P2 | **Plugin trust model** — plugins are Python loaded in-process; manifest permissions gate registry actions but not arbitrary code. Enabling a plugin pins a SHA-256 hash of its `plugin.py`; if the code on disk changes, the plugin refuses to load until the user disables and re-enables it (re-approval). The hash is shown on the plugin card. Full process sandboxing deferred until a marketplace exists. | ✅ done |
| 5 | P2 | **Prompt-injection hardening** — web page text, OCR output, and vision descriptions are wrapped in `<<<UNTRUSTED_CONTENT>>>` delimiters (embedded fakes stripped), and the agent system prompt declares the wrapped region to be data, never instructions. Risk-tier confirmations remain the hard barrier. | ✅ done |
| 6 | P3 | **Electron navigation guards** — `will-navigate` denies anything that isn't local Corvus content, and `setWindowOpenHandler` denies all new windows; http(s) links open in the system browser instead. | ✅ done |
| 7 | P3 | **Tighten CORS** — allowed origins are now `null`/`file://` (packaged renderer) plus the Vite dev-server origins only when running from source (never in a frozen build); moot in depth once item 1 landed. | ✅ done |
| 8 | P3 | **Data at rest** — logging audited: message bodies never reach the log file (transcripts and turns log character counts only). The SQLite database stays plaintext by design — local-first and user-inspectable; revisit SQLCipher/DPAPI-wrapping if secrets-in-chat becomes an expected use. | ✅ done (DB encryption deliberately deferred) |
| 9 | P3 | **Upload endpoint hardening** — `/upload` streams to disk in 1 MB chunks with a 50 MB cap (413 beyond it, partial file removed) and reduces filenames to a safe character set (no separators, no traversal). The input bar also filters by type and size client-side. | ✅ done |
| 10 | P3 | **Supply chain** — Dependabot watches npm (root + frontend), pip, and GitHub Actions weekly; a `security` CI workflow runs the naming guard, `npm audit`, and `pip-audit` on every push/PR and weekly. `npm run audit` runs both npm audits locally. | ✅ done |

Items are checked off in this file in the same commit that implements them.
