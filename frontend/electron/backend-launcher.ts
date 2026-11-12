import { execFile, spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const BACKEND_URL = "http://127.0.0.1:8765";
const RESTART_DELAY_MS = 1000;

let child: ChildProcess | null = null;
let shuttingDown = false;
let restartTimer: NodeJS.Timeout | null = null;

async function isHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

/** /health is open; /session proves the backend was started with *this* launch's token. */
async function acceptsToken(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/session`, {
      headers: { "X-Corvus-Token": token },
      signal: AbortSignal.timeout(1500),
    });
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

/**
 * A backend left over from a crashed launch still serves /health but holds the
 * old token, so every request would 401. Kill it - but only if the listener on
 * our port really is a Corvus backend (corvus-backend.exe, or python in dev).
 */
async function killStaleBackend(): Promise<void> {
  // /health reports the backend's pid (netstat doesn't reliably list the
  // frozen backend's listener). Still verify the image before killing.
  let pid: number | undefined;
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(1500) });
    pid = (await res.json()).pid;
  } catch {
    return;
  }
  if (!Number.isInteger(pid)) return; // an older backend without pid: leave it
  const info = (await run("tasklist", ["/FI", `PID eq ${pid}`, "/FO", "CSV", "/NH"])).toLowerCase();
  // Dev runs under Store Python, whose real process is python3.11.exe.
  if (!/"(corvus-backend|python[\d.]*)\.exe"/.test(info)) return;
  console.warn(`[Corvus] replacing stale backend (pid ${pid})`);
  await run("taskkill", ["/PID", String(pid), "/T", "/F"]);
  for (let i = 0; i < 20 && (await isHealthy()); i++) await new Promise((r) => setTimeout(r, 250));
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
function spawnBackend(isDev: boolean, token: string): void {
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
    // The backend enforces this token on every request (SECURITY.md item 1).
    env: { ...process.env, CORVUS_TOKEN: token },
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
    console.log(`[Corvus] respawning backend in ${RESTART_DELAY_MS}ms`);
    restartTimer = setTimeout(() => {
      restartTimer = null;
      // A backend may have come up in the meantime (e.g. started externally).
      void isHealthy().then((ok) => {
        if (!ok) spawnBackend(isDev, token);
      });
    }, RESTART_DELAY_MS);
  });
}

/**
 * Ensure the backend is running. Reuses one that is already serving (e.g.
 * started manually during development); otherwise spawns and supervises one.
 * Resolves once /health responds or the startup window elapses; the renderer
 * also surfaces live backend status.
 */
export async function startBackend(isDev: boolean, token: string): Promise<boolean> {
  shuttingDown = false;
  if (await isHealthy()) {
    if (await acceptsToken(token)) return true;
    await killStaleBackend();
  }

  spawnBackend(isDev, token);

  for (let i = 0; i < 40; i++) {
    if (await isHealthy()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  console.error("[Corvus] backend did not become healthy within 20s");
  return false;
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
    await fetch(`${BACKEND_URL}/shutdown`, {
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
