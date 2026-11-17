import { defineConfig } from "vitest/config";
import { searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";

/** Strip dev-server origins from the CSP meta tag in production builds. */
const productionCsp = (): Plugin => ({
  name: "corvus-production-csp",
  apply: "build",
  transformIndexHtml: (html) =>
    html.replace(/ (?:ws|http):\/\/(?:localhost|127\.0\.0\.1):5173/g, ""),
});

/** Dev server only: allow the inline React Fast Refresh preamble. */
const devCsp = (): Plugin => ({
  name: "corvus-dev-csp",
  apply: "serve",
  transformIndexHtml: (html) => html.replace("script-src 'self';", "script-src 'self' 'unsafe-inline';"),
});

export default defineConfig({
  plugins: [react(), productionCsp(), devCsp()],
  base: "./",
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    fs: {
      // tokens.json lives one level above the frontend package
      allow: [searchForWorkspaceRoot(process.cwd()), ".."],
    },
  },
  build: { outDir: "dist" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
    include: ["src/**/*.test.{ts,tsx}", "electron/**/*.test.ts"],
  },
});
