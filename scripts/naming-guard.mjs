#!/usr/bin/env node
/**
 * Corvus naming guard.
 * Fails (exit 1) if any tracked text file contains a forbidden placeholder
 * name. The product name is Corvus — nothing else may appear.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..");
const FORBIDDEN = [/colosia/i];
const SKIP_DIRS = new Set([
  ".git",
  "node_modules",
  ".venv",
  "dist",
  "dist-electron",
  "__pycache__",
  ".pytest_cache",
  ".ruff_cache",
  "exports",
]);
const SKIP_EXT = new Set([
  ".png", ".ico", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2",
  ".ttf", ".otf", ".db", ".sqlite", ".zip", ".exe", ".dll", ".pyc", ".lock",
]);

const violations = [];

function scan(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (!SKIP_DIRS.has(entry)) scan(full);
      continue;
    }
    const rel = relative(ROOT, full).split(sep).join("/");
    // The guard itself is the one allowed place the forbidden pattern is spelled out.
    if (rel === "scripts/naming-guard.mjs") continue;
    const ext = entry.includes(".") ? entry.slice(entry.lastIndexOf(".")).toLowerCase() : "";
    if (SKIP_EXT.has(ext) || st.size > 2 * 1024 * 1024) continue;
    const text = readFileSync(full, "utf8");
    const lines = text.split("\n");
    lines.forEach((line, i) => {
      for (const pattern of FORBIDDEN) {
        if (pattern.test(line)) {
          violations.push(`${relative(ROOT, full).split(sep).join("/")}:${i + 1}: ${line.trim()}`);
        }
      }
    });
  }
}

scan(ROOT);

if (violations.length > 0) {
  console.error("Naming guard FAILED — forbidden name found. The product name is Corvus.");
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log("Naming guard passed: no forbidden names found.");
