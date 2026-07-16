import { contextBridge, ipcRenderer } from "electron";

/** Typed bridge available in the renderer as window.corvus. */
const corvusBridge = {
  getSystemTheme: (): Promise<"dark" | "light"> =>
    ipcRenderer.invoke("corvus:get-system-theme"),
  openExternal: (url: string): Promise<void> =>
    ipcRenderer.invoke("corvus:open-external", url),
  openPath: (path: string): Promise<void> =>
    ipcRenderer.invoke("corvus:open-path", path),
  setTitlebarSymbolColor: (color: string): Promise<void> =>
    ipcRenderer.invoke("corvus:set-titlebar-symbol-color", color),
  getVersion: (): Promise<string> => ipcRenderer.invoke("corvus:get-version"),
  getBackendToken: (): Promise<string> => ipcRenderer.invoke("corvus:get-backend-token"),
  checkForUpdates: (): Promise<unknown> => ipcRenderer.invoke("corvus:check-for-updates"),
  installUpdate: (): Promise<void> => ipcRenderer.invoke("corvus:install-update"),
  onUpdateStatus: (callback: (status: UpdateStatus) => void): (() => void) => {
    const listener = (_e: unknown, status: UpdateStatus) => callback(status);
    ipcRenderer.on("corvus:update-status", listener);
    return () => ipcRenderer.removeListener("corvus:update-status", listener);
  },
};

export type UpdateStatus =
  | { state: "checking" }
  | { state: "available"; version: string }
  | { state: "none"; dev?: boolean }
  | { state: "downloading"; percent: number }
  | { state: "downloaded"; version: string }
  | { state: "error"; message: string };

export type CorvusBridge = typeof corvusBridge;

contextBridge.exposeInMainWorld("corvus", corvusBridge);
