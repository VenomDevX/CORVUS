import { contextBridge, ipcRenderer } from "electron";

/** Typed bridge available in the renderer as window.corvus. */
const corvusBridge = {
  getSystemTheme: (): Promise<"dark" | "light"> =>
    ipcRenderer.invoke("corvus:get-system-theme"),
  openExternal: (url: string): Promise<void> =>
    ipcRenderer.invoke("corvus:open-external", url),
  setTitlebarSymbolColor: (color: string): Promise<void> =>
    ipcRenderer.invoke("corvus:set-titlebar-symbol-color", color),
};

export type CorvusBridge = typeof corvusBridge;

contextBridge.exposeInMainWorld("corvus", corvusBridge);
