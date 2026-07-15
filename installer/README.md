# installer/

Milestone 9: packaging Corvus into a Windows `.exe` installer with desktop and
Start Menu shortcuts and auto-update.

## What's here

- `corvus-backend.spec` — PyInstaller spec that freezes the FastAPI backend
  (`corvus.main`) into a standalone `corvus-backend.exe`, collecting the ML
  model/data files it needs (faster-whisper, rapidocr, edge-tts, …).
- The electron-builder config lives at `frontend/electron-builder.yml` (NSIS
  target, icon, shortcuts, and the update `publish` feed).

## Build the installer

Prerequisites: the backend venv with build extras, and frontend deps.

```powershell
# one-time
cd backend; .venv\Scripts\pip install -e .[dev,build]; cd ..
npm install --prefix frontend

# build (from the repo root)
npm run dist
```

`npm run dist` runs two stages:

1. `dist:backend` — PyInstaller freezes the backend to
   `dist-backend/corvus-backend/`.
2. `frontend`'s `dist` — Vite + esbuild build the app, then electron-builder
   packages it, copying the frozen backend into `resources/backend/` (where
   `electron/backend-launcher.ts` looks for `corvus-backend.exe` in production).

Output: `dist-installer/Corvus-Setup-<version>.exe`.

## Auto-update

electron-builder writes `app-update.yml` from the `publish` block in
`frontend/electron-builder.yml`. Point its `url` at your real release host and
upload each build's installer + `latest.yml` there; `electron-updater` (wired in
`electron/updater.ts`) checks it on launch and daily, downloads in the
background, and installs on quit. Signed builds are recommended for a
frictionless update on Windows.

## Notes

- **Playwright's Chromium is not bundled** — the app downloads it on first
  browser use, keeping the installer smaller. Whisper and OCR models likewise
  download on first use.
- The backend is a **Microsoft Store Python** on the current dev machine, which
  virtualizes `%LOCALAPPDATA%`; PyInstaller builds are more reliable from a
  standard (non-Store) Python install. See the environment note in `CLAUDE.md`.
- Code signing is not configured here; add a `win.certificateFile`/`sign` config
  for production releases to avoid SmartScreen warnings.
