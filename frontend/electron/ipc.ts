import { BrowserWindow, app, dialog, ipcMain, nativeTheme, net, shell } from "electron";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { execFile } from "node:child_process";
import { backendPort, backendUrl, nextBackend } from "./backend-launcher";
import { resolveOpenablePath } from "./guards";

function powershell(script: string): Promise<string> {
  return new Promise((resolve) =>
    execFile(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { windowsHide: true, timeout: 60_000 },
      (_err, stdout) => resolve(String(stdout ?? "").trim()),
    ),
  );
}

/** An Authenticode-valid signature whose subject names Ollama's publisher.
 * The installer runs silently, so it must never run unverified. */
async function signedByOllama(file: string): Promise<boolean> {
  const quoted = file.replace(/'/g, "''");
  const out = await powershell(
    `$s = Get-AuthenticodeSignature -LiteralPath '${quoted}'; "$($s.Status)|$($s.SignerCertificate.Subject)"`,
  );
  const [status, subject = ""] = out.split("|");
  return status === "Valid" && /\bO="?Ollama\b/i.test(subject);
}

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
    if (!(await signedByOllama(tempPath))) {
      throw new Error(
        "The downloaded Ollama installer isn't signed by Ollama, so Corvus didn't run it. " +
          "Install Ollama manually from ollama.com.",
      );
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

interface PluginEntry {
  id: string;
  name: string;
  author: string;
  version: string;
  permissions: string[];
  granted_permissions: string[];
  code_hash: string | null;
  enabled: boolean;
}

/** IPC surface exposed to the renderer via preload — keep this minimal and typed. */
export function registerIpc(
  getWindow: () => BrowserWindow | null,
  backendToken: string,
  adminToken: string,
  windows?: { toggleWidget: () => void; showMain: () => void },
) {
  /** Backend call from the main process. `admin` adds the consent secret the
   * renderer never holds - only sent after the user OKs a native dialog. */
  async function backend<T>(route: string, init: RequestInit = {}, admin = false): Promise<T> {
    await backendPort();
    const res = await fetch(`${backendUrl()}${route}`, {
      ...init,
      headers: {
        "X-Corvus-Token": backendToken,
        ...(admin ? { "X-Corvus-Admin": adminToken } : {}),
        ...(init.headers as Record<string, string> | undefined),
      },
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((body as { detail?: string }).detail ?? `backend ${res.status}`);
    return body as T;
  }

  async function confirmDialog(title: string, message: string, detail: string, ok: string) {
    const win = getWindow();
    const options = {
      type: "warning" as const,
      title,
      message,
      detail,
      buttons: [ok, "Cancel"],
      defaultId: 1,
      cancelId: 1,
      noLink: true,
    };
    const { response } = win ? await dialog.showMessageBox(win, options) : await dialog.showMessageBox(options);
    return response === 0;
  }

  async function pluginEntry(pid: string): Promise<PluginEntry> {
    const all = await backend<PluginEntry[]>("/plugins");
    const entry = all.find((p) => p.id === pid);
    if (!entry) throw new Error("plugin not found");
    return entry;
  }

  ipcMain.handle("corvus:toggle-widget", () => windows?.toggleWidget());
  ipcMain.handle("corvus:show-main", () => windows?.showMain());

  ipcMain.handle("corvus:get-system-theme", () =>
    nativeTheme.shouldUseDarkColors ? "dark" : "light",
  );

  // Per-launch backend auth token + the verified port; waits for the
  // handshake, so the renderer never talks to an unverified listener.
  ipcMain.handle("corvus:get-backend-info", async () => ({
    token: backendToken,
    port: await backendPort(),
  }));

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
    const baseDir = path.join(process.env.LOCALAPPDATA ?? os.homedir(), "Corvus");
    const decision = resolveOpenablePath(target, baseDir);
    if (decision.kind === "blocked") {
      console.warn(`Blocked attempt to open path outside data dir: ${target}`);
      return;
    }
    if (decision.kind === "reveal") shell.showItemInFolder(decision.path);
    else await shell.openPath(decision.path);
  });

  ipcMain.handle("corvus:set-titlebar-symbol-color", (_event, color: string) => {
    const win = getWindow();
    if (win && /^#[0-9A-Fa-f]{6,8}$/.test(color)) {
      win.setTitleBarOverlay({ color: "#00000000", symbolColor: color, height: 40 });
    }
  });

  // -- Consent moments: native dialogs the renderer can't fake or skip ------

  ipcMain.handle("corvus:plugin-install", async () => {
    const win = getWindow();
    const options = {
      title: "Add a Corvus plugin",
      filters: [{ name: "Corvus plugin", extensions: ["zip"] }],
      properties: ["openFile" as const],
    };
    const picked = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options);
    if (picked.canceled || !picked.filePaths[0]) return null;
    const file = picked.filePaths[0];
    const form = new FormData();
    form.append("file", new Blob([fs.readFileSync(file)]), path.basename(file));
    // Installing is admin-gated too: it lands disabled, but writes code to disk.
    return backend("/plugins/install", { method: "POST", body: form }, true);
  });

  ipcMain.handle("corvus:plugin-enable", async (_event, pid: string) => {
    const p = await pluginEntry(String(pid));
    const perms = p.permissions.length ? p.permissions.join(", ") : "none";
    const ok = await confirmDialog(
      "Enable plugin",
      `Enable “${p.name}” v${p.version} by ${p.author}?`,
      `Plugins run with full access to your computer.\n\nPermissions it asks for: ${perms}\n` +
        `Code hash: ${p.code_hash ?? "unknown"}\n\nOnly enable plugins from people you trust.`,
      "Enable",
    );
    if (!ok) return { loaded: false, error: null, cancelled: true };
    return backend(`/plugins/${encodeURIComponent(p.id)}/enable`, { method: "POST" }, true);
  });

  ipcMain.handle("corvus:plugin-set-permissions", async (_event, pid: string, permissions: string[]) => {
    const p = await pluginEntry(String(pid));
    const wanted = (Array.isArray(permissions) ? permissions : []).map(String);
    const added = wanted.filter((perm) => !p.granted_permissions.includes(perm));
    if (added.length) {
      const ok = await confirmDialog(
        "Grant permission",
        `Let “${p.name}” use: ${added.join(", ")}?`,
        "Granting a permission lets the plugin's code use that capability on this computer.",
        "Grant",
      );
      if (!ok) return { ok: false, granted: p.granted_permissions, cancelled: true };
    }
    return backend(
      `/plugins/${encodeURIComponent(p.id)}/permissions`,
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ permissions: wanted }) },
      true,
    );
  });

  ipcMain.handle("corvus:wipe-data", async () => {
    const ok = await confirmDialog(
      "Delete all my data",
      "Delete everything Corvus has stored on this computer?",
      "This permanently removes your conversations, memories, workflows, reminders, saved API keys, " +
        "generated media, uploads, screenshots, downloads, document index and installed plugins. " +
        "It can't be undone - export a backup first if you might want it back.",
      "Delete everything",
    );
    if (!ok) return { ok: false, cancelled: true };
    const restarted = nextBackend();
    await backend("/data/wipe", { method: "POST" }, true);
    // The backend exits after wiping; the supervisor respawns a fresh one.
    // Reload every window once it's verified so nothing shows stale data.
    void restarted.then(() => {
      for (const w of BrowserWindow.getAllWindows()) w.webContents.reload();
    });
    return { ok: true };
  });
}
