import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const BACKEND_URL = "http://127.0.0.1:8765";
let child: ChildProcess | null = null;

async function isHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Spawn the FastAPI backend unless one is already serving (e.g. started
 * manually during development). Resolves once /health responds or the
 * startup window elapses; the renderer also surfaces live backend status.
 */
export async function startBackend(isDev: boolean): Promise<boolean> {
  if (await isHealthy()) return true;

  const repoRoot = join(__dirname, "..", "..");
  const python = isDev
    ? join(repoRoot, "backend", ".venv", "Scripts", "python.exe")
    : join(process.resourcesPath, "backend", "corvus-backend.exe");

  if (!existsSync(python)) {
    console.error(`[Corvus] backend runtime not found at ${python}`);
    return false;
  }

  const args = isDev ? ["-m", "corvus.main"] : [];
  child = spawn(python, args, {
    cwd: isDev ? join(repoRoot, "backend") : undefined,
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("exit", (code) => {
    console.log(`[Corvus] backend exited with code ${code}`);
    child = null;
  });

  for (let i = 0; i < 40; i++) {
    if (await isHealthy()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  console.error("[Corvus] backend did not become healthy within 20s");
  return false;
}

export function stopBackend() {
  if (child && !child.killed) child.kill();
  child = null;
}
