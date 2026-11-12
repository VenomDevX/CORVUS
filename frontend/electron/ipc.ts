import { BrowserWindow, app, ipcMain, nativeTheme, net, shell } from "electron";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { execFile } from "node:child_process";
const OPENABLE_EXTS = new Set([
  ".pdf", ".txt", ".md", ".csv", ".json", ".rtf",
  ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
  ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4", ".webm", ".mkv", ".mov", ".avi",
  ".zip",
]);

/** Download and silently run the Ollama installer; errors carry user-facing text. */
async function installOllama(): Promise<boolean> {
  const tempPath = path.join(app.getPath("temp"), `OllamaSetup-${Date.now()}.exe`);
  try {
    let response: Response;
    try {
      // net.fetch follows redirects; ollama.com 307s to the GitHub release asset.
      response = await net.fetch("https://ollama.com/download/OllamaSetup.exe");
    } catch {
      throw new Error("Couldn't download Ollama. Check your internet connection and try again.");
    }
    if (!response.ok || !response.body) {
      throw new Error(`Couldn't download Ollama (server returned ${response.status}). Try again later.`);
    }
    try {
      await pipeline(Readable.fromWeb(response.body as any), fs.createWriteStream(tempPath));
    } catch {
      throw new Error("The Ollama download was interrupted. Check your connection and try again.");
    }
    await new Promise<void>((resolve, reject) =>
      execFile(
        tempPath,
        ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        { timeout: 10 * 60 * 1000 },
        (error) =>
          error
            ? reject(new Error("The Ollama installer was cancelled or failed. Try installing it manually."))
            : resolve(),
      ),
    );
    return true;
  } finally {
    fs.unlink(tempPath, () => {});
  }
}

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

  // One install at a time: Settings and onboarding both have an install button,
  // and a second click must not truncate the installer the first is writing.
  let ollamaInstall: Promise<boolean> | null = null;
  ipcMain.handle("corvus:install-ollama", () => {
    ollamaInstall ??= installOllama().finally(() => {
      ollamaInstall = null;
    });
    return ollamaInstall;
  });

  ipcMain.handle("corvus:open-external", async (_event, url: string) => {
    if (/^https?:\/\//.test(url)) await shell.openExternal(url);
  });

  ipcMain.handle("corvus:open-path", async (_event, target: string) => {
    // Local files Corvus created (e.g. browser downloads); shell picks the app.
    // Windows drops trailing dots/spaces ("x.exe." opens x.exe), so trim before checking.
    const normalized = path.normalize(String(target)).replace(/[. ]+$/, "");

    // Restrict to the Corvus data dir (where downloads and uploads live).
    // Compare case-insensitively (NTFS) and require the separator so a
    // sibling like ...\CorvusEvil can't pass a bare prefix check.
    const baseDir = path.join(process.env.LOCALAPPDATA ?? os.homedir(), "Corvus");
    if (!normalized.toLowerCase().startsWith(baseDir.toLowerCase() + path.sep)) {
      console.warn(`Blocked attempt to open path outside data dir: ${target}`);
      return;
    }

    // Websites pick download names, so only open known document/media types.
    // Anything else (.hta, .js, .lnk, .exe, …) is revealed in Explorer, not run.
    if (!OPENABLE_EXTS.has(path.extname(normalized).toLowerCase())) {
      shell.showItemInFolder(normalized);
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
