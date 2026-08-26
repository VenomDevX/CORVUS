import { BrowserWindow, app, ipcMain, nativeTheme, shell } from "electron";
import * as fs from "node:fs";
import * as path from "node:path";
import * as https from "node:https";
import { execFile } from "node:child_process";
/** IPC surface exposed to the renderer via preload — keep this minimal and typed. */
export function registerIpc(
  getWindow: () => BrowserWindow | null,
  backendToken: string,
  windows?: { toggleWidget: () => void; showMain: () => void },
) {
  ipcMain.handle("corvus:toggle-widget", () => windows?.toggleWidget());
  ipcMain.handle("corvus:show-main", () => windows?.showMain());

  ipcMain.handle("corvus:get-system-theme", () =>
    nativeTheme.shouldUseDarkColors ? "dark" : "light",
  );

  // Per-launch backend auth token; the renderer attaches it to every request.
  ipcMain.handle("corvus:get-backend-token", () => backendToken);

  ipcMain.handle("corvus:get-version", () => app.getVersion());

  ipcMain.handle("corvus:install-ollama", async () => {
    return new Promise((resolve, reject) => {
      const downloadUrl = "https://ollama.com/download/OllamaSetup.exe";
      const tempPath = path.join(app.getPath("temp"), "OllamaSetup.exe");
      
      const file = fs.createWriteStream(tempPath);
      https.get(downloadUrl, (response) => {
        if (response.statusCode !== 200) {
          return reject(new Error("Failed to download Ollama. Status: " + response.statusCode));
        }
        response.pipe(file);
        file.on("finish", () => {
          file.close();
          // Execute silently
          execFile(tempPath, ["/SILENT"], (error) => {
            if (error) {
              reject(error);
            } else {
              resolve(true);
            }
          });
        });
      }).on("error", (err) => {
        fs.unlink(tempPath, () => {});
        reject(err);
      });
    });
  });

  ipcMain.handle("corvus:open-external", async (_event, url: string) => {
    if (/^https?:\/\//.test(url)) await shell.openExternal(url);
  });

  ipcMain.handle("corvus:open-path", async (_event, path: string) => {
    // Local files Corvus created (e.g. browser downloads); shell picks the app.
    const normalized = require("node:path").normalize(path);
    const ext = require("node:path").extname(normalized).toLowerCase();
    
    // Block executable extensions
    const BLOCKED_EXTS = [".exe", ".bat", ".cmd", ".vbs", ".ps1", ".scr", ".pif", ".msi", ".com"];
    if (BLOCKED_EXTS.includes(ext)) {
      console.warn(`Blocked attempt to open executable file: ${path}`);
      return;
    }

    // Restrict to the Corvus data dir (where downloads and uploads live).
    // Compare case-insensitively (NTFS) and require the separator so a
    // sibling like ...\CorvusEvil can't pass a bare prefix check.
    const sep = require("node:path").sep;
    const baseDir = process.env.LOCALAPPDATA
      ? require("node:path").join(process.env.LOCALAPPDATA, "Corvus")
      : require("node:path").join(require("node:os").homedir(), "Corvus");
    const inBase = normalized.toLowerCase().startsWith(baseDir.toLowerCase() + sep);
    if (!inBase) {
      console.warn(`Blocked attempt to open path outside data dir: ${path}`);
      return;
    }

    await shell.openPath(normalized);
  });

  ipcMain.handle("corvus:set-titlebar-symbol-color", (_event, color: string) => {
    const win = getWindow();
    if (win && /^#[0-9A-Fa-f]{6,8}$/.test(color)) {
      win.setTitleBarOverlay({ color: "#00000000", symbolColor: color, height: 40 });
    }
  });
}
