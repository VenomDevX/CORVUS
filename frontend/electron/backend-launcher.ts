import { spawn, type ChildProcess } from "node:child_process";
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
function spawnBackend(isDev: boolean): void {
  if (shuttingDown || (child && !child.killed)) return;

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
  });

  child.on("exit", (code) => {
    console.log(`[Corvus] backend exited with code ${code}`);
    child = null;
    if (shuttingDown || restartTimer) return;
    console.log(`[Corvus] respawning backend in ${RESTART_DELAY_MS}ms`);
    restartTimer = setTimeout(() => {
      restartTimer = null;
      // A backend may have come up in the meantime (e.g. started externally).
      void isHealthy().then((ok) => {
        if (!ok) spawnBackend(isDev);
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
export async function startBackend(isDev: boolean): Promise<boolean> {
  shuttingDown = false;
  if (await isHealthy()) return true;

  spawnBackend(isDev);

  for (let i = 0; i < 40; i++) {
    if (await isHealthy()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  console.error("[Corvus] backend did not become healthy within 20s");
  return false;
}

export function stopBackend() {
  shuttingDown = true;
  if (restartTimer) {
    clearTimeout(restartTimer);
    restartTimer = null;
  }
  if (child && !child.killed) child.kill();
  child = null;
}
