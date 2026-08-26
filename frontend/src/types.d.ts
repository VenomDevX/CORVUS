export type CorvusBridge = {
  getSystemTheme: () => Promise<"dark" | "light">;
  openExternal: (url: string) => Promise<void>;
  openPath: (path: string) => Promise<void>;
  setTitlebarSymbolColor: (color: string) => Promise<void>;
  getVersion: () => Promise<string>;
  getBackendToken: () => Promise<string>;
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
