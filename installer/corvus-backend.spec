# PyInstaller spec: freeze the Corvus backend into a standalone folder.
#
# Build (from the repo root, with the backend venv active):
#   cd backend && ..\backend\.venv\Scripts\pyinstaller ..\installer\corvus-backend.spec \
#       --distpath ..\dist-backend --workpath ..\build\pyinstaller
#
# Produces dist-backend/corvus-backend/corvus-backend.exe, which electron-builder
# copies into the app's resources/backend (see frontend/electron-builder.yml).
#
# The heavy ML deps (faster-whisper/ctranslate2, rapidocr/onnxruntime, edge-tts)
# ship their model/data files, collected below. Playwright's Chromium is NOT
# bundled - the app downloads it on first browser use to keep the installer
# smaller.

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

for package in (
    "faster_whisper",
    "ctranslate2",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "edge_tts",
    "sounddevice",
    "miniaudio",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["corvus.main", "pyautogui", "PIL.ImageGrab"]


a = Analysis(
    ["../backend/corvus/main.py"],
    pathex=["../backend"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="corvus-backend",
    console=True,
    disable_windowed_traceback=False,
    icon="../design/exports/corvus.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="corvus-backend",
)
