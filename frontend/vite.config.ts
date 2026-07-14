import { defineConfig } from "vitest/config";
import { searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
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
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
