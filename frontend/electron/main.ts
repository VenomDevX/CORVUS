import { app, BrowserWindow, globalShortcut, nativeTheme } from "electron";
import { join } from "node:path";
import { createTray, destroyTray } from "./tray";
import { registerIpc } from "./ipc";
import { startBackend, stopBackend } from "./backend-launcher";
import { initAutoUpdate } from "./updater";

const DEV_URL = "http://127.0.0.1:5173";
const isDev = !app.isPackaged;

let mainWindow: BrowserWindow | null = null;
let quitting = false;

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
    registerIpc(() => mainWindow);
    createWindow();
    createTray({
      onShow: showMainWindow,
      onQuit: () => {
        quitting = true;
        app.quit();
      },
      iconPath: (variant: "light" | "dark", size: 16 | 32) =>
        assetPath(`tray-${variant}-${size}.png`),
    });
    globalShortcut.register("Control+Shift+C", showMainWindow);
    void startBackend(isDev);
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
