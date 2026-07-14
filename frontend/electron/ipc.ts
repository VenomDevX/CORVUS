import { BrowserWindow, ipcMain, nativeTheme, shell } from "electron";

/** IPC surface exposed to the renderer via preload — keep this minimal and typed. */
export function registerIpc(getWindow: () => BrowserWindow | null) {
  ipcMain.handle("corvus:get-system-theme", () =>
    nativeTheme.shouldUseDarkColors ? "dark" : "light",
  );

  ipcMain.handle("corvus:open-external", async (_event, url: string) => {
    if (/^https?:\/\//.test(url)) await shell.openExternal(url);
  });

  ipcMain.handle("corvus:set-titlebar-symbol-color", (_event, color: string) => {
    const win = getWindow();
    if (win && /^#[0-9A-Fa-f]{6,8}$/.test(color)) {
      win.setTitleBarOverlay({ color: "#00000000", symbolColor: color, height: 40 });
    }
  });
}
