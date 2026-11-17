import { execFile, spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { join } from "node:path";
import { BrowserWindow } from "electron";
import { verifyBackend } from "./guards";

const RESTART_DELAY_MS = 1000;

let child: ChildProcess | null = null;
let shuttingDown = false;
let restartTimer: NodeJS.Timeout | null = null;
let port = 0;

/** Resolves with the port once a backend has passed the handshake; replaced
 * (pending again) while a respawned backend comes up. */
let ready!: Promise<number>;
let markReady!: (p: number) => void;
function resetReady() {
  ready = new Promise((resolve) => (markReady = resolve));
}
resetReady();

export const backendUrl = () => `http://127.0.0.1:${port}`;
export const backendPort = (): Promise<number> => ready;

/** Resolves the next time a (re)spawned backend passes the handshake. */
const restartWaiters: ((p: number) => void)[] = [];
export const nextBackend = (): Promise<number> => new Promise((r) => restartWaiters.push(r));

/** A free loopback port, picked fresh per launch: a fixed, well-known port
 * could be squatted by another local process before Corvus starts. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const address = srv.address();
      srv.close(() => (typeof address === "object" && address ? resolve(address.port) : reject()));
    });
  });
}

async function isHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${backendUrl()}/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

function run(cmd: string, args: string[]): Promise<string> {
  return new Promise((resolve) =>
    execFile(cmd, args, { windowsHide: true }, (_err, stdout) => resolve(stdout ?? "")),
  );
}

function backendPath(isDev: boolean): string {
  const repoRoot = join(__dirname, "..", "..");
  return isDev
    ? join(repoRoot, "backend", ".venv", "Scripts", "python.exe")
    : join(process.resourcesPath, "backend", "corvus-backend.exe");
}

/**
 * Spawn a single backend process and supervise it: if it exits while the app
 * is still running, respawn it after a short delay. Quitting the app sets
 * `shuttingDown`, which suppresses the respawn.
 */
function spawnBackend(isDev: boolean, token: string, adminToken: string): void {
  if (shuttingDown || child) return;

  const python = backendPath(isDev);
  if (!existsSync(python)) {
    console.error(`[Corvus] backend runtime not found at ${python}`);
    return;
  }

  const repoRoot = join(__dirname, "..", "..");
  const args = isDev ? ["-m", "corvus.main"] : [];
  child = spawn(python, args, {
    cwd: isDev ? join(repoRoot, "backend") : undefined,
    stdio: "inherit",
    windowsHide: true,
    env: {
      ...process.env,
      CORVUS_PORT: String(port),
      CORVUS_TOKEN: token,
      // Second secret for consent routes (plugin approval, data wipe); the
      // renderer never sees it.
      CORVUS_ADMIN_TOKEN: adminToken,
      // The backend exits when we do, so a crash never leaves an orphan.
      CORVUS_PARENT_PID: String(process.pid),
    },
  });

  const spawned = child;
  // Spawn failures (EACCES/EPERM from antivirus, a locked exe mid-update) come
  // as 'error', not 'exit': without a handler they crash the main process.
  spawned.on("error", (err) => {
    console.error(`[Corvus] backend failed to start: ${err.message}`);
    spawned.emit("exit", null);
  });
  spawned.on("exit", (code) => {
    if (child !== spawned) return; // already handled, or an older process
    console.log(`[Corvus] backend exited with code ${code}`);
    child = null;
    if (shuttingDown || restartTimer) return;
    resetReady();
    // The old port is free now and any local process may bind it: tell the
    // renderer to stop using it before it sends the token there.
    for (const w of BrowserWindow.getAllWindows()) w.webContents.send("corvus:backend-lost");
    console.log(`[Corvus] respawning backend in ${RESTART_DELAY_MS}ms`);
    restartTimer = setTimeout(() => {
      restartTimer = null;
      void launch(isDev, token, adminToken);
    }, RESTART_DELAY_MS);
  });
}

async function launch(isDev: boolean, token: string, adminToken: string): Promise<boolean> {
  port = await freePort();
  spawnBackend(isDev, token, adminToken);
  for (let i = 0; i < 40; i++) {
    if (await isHealthy()) {
      // Anything could be answering /health on this port; only a backend that
      // proves it holds this launch's token gets the renderer's traffic.
      if (await verifyBackend(backendUrl(), token, randomBytes(16).toString("hex"))) {
        console.log(`[Corvus] backend verified on port ${port}`);
        markReady(port);
        for (const waiter of restartWaiters.splice(0)) waiter(port);
        return true;
      }
      console.error("[Corvus] listener on the backend port failed the handshake");
      return false;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  console.error("[Corvus] backend did not become healthy within 20s");
  return false;
}

/** Spawn, supervise and verify the backend. Resolves once it passed the
 * handshake (true) or the startup window elapsed (false). */
export async function startBackend(isDev: boolean, token: string, adminToken: string): Promise<boolean> {
  shuttingDown = false;
  return launch(isDev, token, adminToken);
}

/**
 * Ask the backend to exit gracefully (so its shutdown hook marks the session
 * clean), then force-kill if it hasn't exited within a few seconds. On Windows
 * child.kill() is TerminateProcess, which skips that hook.
 */
export async function stopBackend(token: string): Promise<void> {
  shuttingDown = true;
  if (restartTimer) {
    clearTimeout(restartTimer);
    restartTimer = null;
  }
  const proc = child;
  child = null;
  if (!proc || proc.exitCode !== null) return;
  const exited = new Promise<void>((r) => proc.once("exit", () => r()));
  try {
    await fetch(`${backendUrl()}/shutdown`, {
      method: "POST",
      headers: { "X-Corvus-Token": token },
      signal: AbortSignal.timeout(1500),
    });
    // Backend budget: ≤3s draining connections + ≤3s stopping voice + closing the rest.
    await Promise.race([exited, new Promise((r) => setTimeout(r, 8000))]);
  } catch {
    // Backend unresponsive - fall through to the kill.
  }
  // Kill the whole tree: the venv python.exe (dev) is only a launcher for the
  // real interpreter, and child.kill() would leave that holding the port.
  if (proc.exitCode === null && proc.pid) await run("taskkill", ["/PID", String(proc.pid), "/T", "/F"]);
}
