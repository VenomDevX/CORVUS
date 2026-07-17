import { app, BrowserWindow, globalShortcut, nativeTheme, screen, shell } from "electron";
import { randomBytes } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createTray, destroyTray } from "./tray";
import { registerIpc } from "./ipc";
import { startBackend, stopBackend } from "./backend-launcher";
import { initAutoUpdate } from "./updater";

const DEV_URL = "http://127.0.0.1:5173";
const isDev = !app.isPackaged;

let mainWindow: BrowserWindow | null = null;
let widgetWindow: BrowserWindow | null = null;
let quitting = false;

// Per-launch token every backend request must present (SECURITY.md item 1).
// The spawned backend receives it via CORVUS_TOKEN; the renderer via IPC.
const backendToken = randomBytes(32).toString("hex");

function assetPath(...parts: string[]) {
  // dist-electron/ sits inside frontend/; design assets live at the repo root.
  return join(__dirname, "..", "..", "design", "exports", ...parts);
}

export function showMainWindow() {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

const WIDGET_SIZE = { width: 400, height: 180 };
const widgetPosFile = () => join(app.getPath("userData"), "widget.json");

function savedWidgetPos(): { x: number; y: number } | null {
  try {
    const pos = JSON.parse(readFileSync(widgetPosFile(), "utf8")) as { x: number; y: number };
    if (Number.isFinite(pos.x) && Number.isFinite(pos.y)) return pos;
  } catch {
    /* first run or corrupt file — use the default corner */
  }
  return null;
}

/** Navigation guards (SECURITY.md item 6): every Corvus window only ever
 * shows local Corvus content; http(s) links open in the system browser. */
function applyNavigationGuards(win: BrowserWindow) {
  win.webContents.on("will-navigate", (event, url) => {
    const allowed = isDev ? url.startsWith(DEV_URL) : url.startsWith("file://");
    if (!allowed) {
      event.preventDefault();
      if (/^https?:\/\//.test(url)) void shell.openExternal(url);
    }
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
}

export function toggleWidgetWindow() {
  if (widgetWindow) {
    widgetWindow.close();
    return;
  }
  const work = screen.getPrimaryDisplay().workArea;
  const fallback = {
    x: work.x + work.width - WIDGET_SIZE.width - 24,
    y: work.y + work.height - WIDGET_SIZE.height - 24,
  };
  const pos = savedWidgetPos() ?? fallback;
  widgetWindow = new BrowserWindow({
    ...WIDGET_SIZE,
    x: pos.x,
    y: pos.y,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    icon: assetPath("corvus.ico"),
    webPreferences: {
      preload: join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  widgetWindow.setMenuBarVisibility(false);
  applyNavigationGuards(widgetWindow);
  if (isDev) void widgetWindow.loadURL(`${DEV_URL}/#/widget`);
  else void widgetWindow.loadFile(join(__dirname, "..", "dist", "index.html"), { hash: "/widget" });
  widgetWindow.on("moved", () => {
    const [x, y] = widgetWindow?.getPosition() ?? [];
    if (x !== undefined) {
      try {
        writeFileSync(widgetPosFile(), JSON.stringify({ x, y }));
      } catch {
        /* position just won't persist */
      }
    }
  });
  widgetWindow.on("closed", () => {
    widgetWindow = null;
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    title: "Corvus",
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#05060A",
    backgroundMaterial: "mica",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#00000000",
      symbolColor: nativeTheme.shouldUseDarkColors ? "#F5F7FA" : "#0B1220",
      height: 40,
    },
    icon: assetPath("corvus.ico"),
    webPreferences: {
      preload: join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setMenuBarVisibility(false);

  applyNavigationGuards(mainWindow);

  if (isDev) {
    void mainWindow.loadURL(DEV_URL);
  } else {
    void mainWindow.loadFile(join(__dirname, "..", "dist", "index.html"));
  }

  // Close-to-tray: Corvus keeps running in the background.
  mainWindow.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", showMainWindow);

  app.whenReady().then(() => {
    registerIpc(() => mainWindow, backendToken, {
      toggleWidget: toggleWidgetWindow,
      showMain: showMainWindow,
    });
    createWindow();
    createTray({
      onShow: showMainWindow,
      onToggleWidget: toggleWidgetWindow,
      onQuit: () => {
        quitting = true;
        app.quit();
      },
      iconPath: (variant: "light" | "dark", size: 16 | 32) =>
        assetPath(`tray-${variant}-${size}.png`),
    });
    globalShortcut.register("Control+Shift+C", showMainWindow);
    // Alt+Space summons Corvus over any app; pressing it again tucks it away.
    const altSpaceOk = globalShortcut.register("Alt+Space", () => {
      if (mainWindow?.isVisible() && mainWindow.isFocused()) mainWindow.hide();
      else showMainWindow();
    });
    if (!altSpaceOk) console.warn("Alt+Space is taken by another app; Ctrl+Shift+C still works.");
    void startBackend(isDev, backendToken);
    void initAutoUpdate(() => mainWindow, isDev);
  });

  app.on("before-quit", () => {
    quitting = true;
  });

  app.on("will-quit", () => {
    globalShortcut.unregisterAll();
    destroyTray();
    stopBackend();
  });

  app.on("window-all-closed", () => {
    // Tray keeps the app alive; explicit Quit ends it.
    if (quitting) app.quit();
  });
}
