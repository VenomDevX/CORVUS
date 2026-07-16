import { BrowserWindow, app, ipcMain, nativeTheme, shell } from "electron";

/** IPC surface exposed to the renderer via preload — keep this minimal and typed. */
export function registerIpc(getWindow: () => BrowserWindow | null, backendToken: string) {
  ipcMain.handle("corvus:get-system-theme", () =>
    nativeTheme.shouldUseDarkColors ? "dark" : "light",
  );

  // Per-launch backend auth token; the renderer attaches it to every request.
  ipcMain.handle("corvus:get-backend-token", () => backendToken);

  ipcMain.handle("corvus:get-version", () => app.getVersion());

  ipcMain.handle("corvus:open-external", async (_event, url: string) => {
    if (/^https?:\/\//.test(url)) await shell.openExternal(url);
  });

  ipcMain.handle("corvus:open-path", async (_event, path: string) => {
    // Local files Corvus created (e.g. browser downloads); shell picks the app.
    await shell.openPath(path);
  });

  ipcMain.handle("corvus:set-titlebar-symbol-color", (_event, color: string) => {
    const win = getWindow();
    if (win && /^#[0-9A-Fa-f]{6,8}$/.test(color)) {
      win.setTitleBarOverlay({ color: "#00000000", symbolColor: color, height: 40 });
    }
  });
}
