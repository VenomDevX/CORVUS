import type { CorvusBridge } from "../electron/preload";

declare global {
  interface Window {
    /** Present only inside Electron; absent when running plain Vite in a browser. */
    corvus?: CorvusBridge;
  }
}

export {};
