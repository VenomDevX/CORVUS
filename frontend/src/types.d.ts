export type CorvusBridge = {
  getSystemTheme: () => Promise<"dark" | "light">;
  openExternal: (url: string) => Promise<void>;
  openPath: (path: string) => Promise<void>;
  setTitlebarSymbolColor: (color: string) => Promise<void>;
  getVersion: () => Promise<string>;
  getBackendInfo: () => Promise<{ token: string; port: number }>;
  onBackendLost?: (callback: () => void) => void;
  installPlugin: () => Promise<unknown>;
  enablePlugin: (id: string) => Promise<{ loaded: boolean; error: string | null; cancelled?: boolean }>;
  setPluginPermissions: (id: string, permissions: string[]) => Promise<{ ok: boolean; cancelled?: boolean }>;
  wipeData: () => Promise<{ ok: boolean; cancelled?: boolean }>;
  toggleWidget: () => Promise<void>;
  showMain: () => Promise<void>;
  checkForUpdates: () => Promise<unknown>;
  installUpdate: () => Promise<void>;
  installOllama: () => Promise<boolean>;
  onUpdateStatus: (callback: (status: any) => void) => () => void;
};

declare global {
  interface Window {
    /** Present only inside Electron; absent when running plain Vite in a browser. */
    corvus?: CorvusBridge;
  }
}

export {};
