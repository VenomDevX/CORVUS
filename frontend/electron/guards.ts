import { createHmac } from "node:crypto";
import * as path from "node:path";

/** Pure security checks for the main process, kept free of Electron imports
 * so vitest can exercise them directly. */

export const OPENABLE_EXTS = new Set([
  ".pdf", ".txt", ".md", ".csv", ".json", ".rtf",
  ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
  ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4", ".webm", ".mkv", ".mov", ".avi",
  ".zip",
]);

function originOf(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/** Every Corvus window may only show Corvus's own page: the Vite dev origin
 * in dev, or exactly the bundled index.html when packaged. Any other file://
 * URL (a downloaded .html, a UNC share) would get the preload bridge and with
 * it the backend token. */
export function isAllowedNavigation(url: string, devUrl: string | null, appIndexPath: string): boolean {
  if (devUrl) return originOf(url) === originOf(devUrl);
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== "file:" || parsed.host !== "") return false; // no UNC hosts
  // file:///C:/x/index.html -> "C:/x/index.html"
  const target = decodeURIComponent(parsed.pathname).replace(/^\/([A-Za-z]:)/, "$1");
  return path.win32.normalize(target).toLowerCase() === path.win32.normalize(appIndexPath).toLowerCase();
}

export type OpenDecision = { kind: "open" | "reveal"; path: string } | { kind: "blocked" };

/** Decide what `corvus:open-path` may do with a renderer-supplied path: only
 * files under the Corvus data dir; known document/media types open, anything
 * else (.exe, .hta, .lnk…) is only revealed in Explorer. */
export function resolveOpenablePath(target: string, baseDir: string): OpenDecision {
  // Windows drops trailing dots/spaces ("x.exe." opens x.exe), so trim before checking.
  const normalized = path.win32.normalize(String(target)).replace(/[. ]+$/, "");
  // Case-insensitive (NTFS), separator required so ...\CorvusEvil can't pass.
  const base = path.win32.normalize(baseDir).replace(/\\+$/, "") + "\\";
  if (!normalized.toLowerCase().startsWith(base.toLowerCase())) return { kind: "blocked" };
  if (normalized.includes("\0")) return { kind: "blocked" };
  return OPENABLE_EXTS.has(path.win32.extname(normalized).toLowerCase())
    ? { kind: "open", path: normalized }
    : { kind: "reveal", path: normalized };
}

/** The HMAC a genuine backend returns from /handshake for this nonce. */
export function expectedHandshake(token: string, nonce: string): string {
  return createHmac("sha256", token).update(nonce).digest("hex");
}

/** True only if the listener at `baseUrl` proves it holds `token`. */
export async function verifyBackend(
  baseUrl: string,
  token: string,
  nonce: string,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  try {
    const res = await fetchImpl(`${baseUrl}/handshake?nonce=${encodeURIComponent(nonce)}`, {
      signal: AbortSignal.timeout(1500),
    });
    if (!res.ok) return false;
    const body = (await res.json()) as { hmac?: unknown };
    return typeof body.hmac === "string" && body.hmac === expectedHandshake(token, nonce);
  } catch {
    return false;
  }
}

/** Header CSP: dev origins only in dev; backend on any loopback port (it's
 * random per launch and verified by handshake before the renderer uses it). */
export function contentSecurityPolicy(isDev: boolean): string {
  const dev = isDev ? " ws://localhost:5173 http://localhost:5173 ws://127.0.0.1:5173" : "";
  return [
    "default-src 'self'",
    // Dev only: Vite injects React Fast Refresh as an inline preamble script.
    isDev ? "script-src 'self' 'unsafe-inline'" : "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: http://127.0.0.1:*",
    "media-src 'self' blob: http://127.0.0.1:*",
    `connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*${dev}`,
  ].join("; ");
}
