import { BrowserWindow, ipcMain } from "electron";
import type { AppUpdater } from "electron-updater";

/**
 * Auto-update via electron-updater. In production the updater checks the
 * configured release feed (see build.publish in package.json); it downloads in
 * the background and installs on quit. The renderer drives the UI through the
 * IPC surface below and receives status via the "corvus:update-status" channel.
 *
 * In dev there is no update feed, so checks are skipped gracefully.
 */

type UpdateStatus =
  | { state: "checking" }
  | { state: "available"; version: string }
  | { state: "none" }
  | { state: "downloading"; percent: number }
  | { state: "downloaded"; version: string }
  | { state: "error"; message: string };

let updater: AppUpdater | null = null;

async function loadUpdater(): Promise<AppUpdater | null> {
  try {
    // Lazily required so dev (unpackaged) runs don't need the module resolved.
    const { autoUpdater } = await import("electron-updater");
    return autoUpdater;
  } catch {
    return null;
  }
}

export async function initAutoUpdate(getWindow: () => BrowserWindow | null, isDev: boolean) {
  const send = (status: UpdateStatus) =>
    getWindow()?.webContents.send("corvus:update-status", status);

  ipcMain.handle("corvus:check-for-updates", async () => {
    if (isDev) return { state: "none", dev: true };
    if (!updater) updater = await loadUpdater();
    if (!updater) return { state: "error", message: "updater unavailable" };
    try {
      await updater.checkForUpdates();
      return { state: "checking" };
    } catch (err) {
      return { state: "error", message: String(err) };
    }
  });

  ipcMain.handle("corvus:install-update", async () => {
    if (updater) updater.quitAndInstall();
  });

  if (isDev) return;

  updater = await loadUpdater();
  if (!updater) return;

  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = true;
  updater.on("checking-for-update", () => send({ state: "checking" }));
  updater.on("update-available", (info) => send({ state: "available", version: info.version }));
  updater.on("update-not-available", () => send({ state: "none" }));
  updater.on("download-progress", (p) => send({ state: "downloading", percent: Math.round(p.percent) }));
  updater.on("update-downloaded", (info) => send({ state: "downloaded", version: info.version }));
  updater.on("error", (err) => send({ state: "error", message: String(err) }));

  // Check shortly after launch, then daily.
  setTimeout(() => void updater?.checkForUpdates().catch(() => {}), 8000);
  setInterval(() => void updater?.checkForUpdates().catch(() => {}), 24 * 60 * 60 * 1000);
}
