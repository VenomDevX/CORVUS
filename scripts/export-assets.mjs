#!/usr/bin/env node
/**
 * Corvus asset export pipeline.
 * Renders the SVG sources in design/logo/ to every raster asset the app and
 * (later) installer consume: PNGs at all icon sizes, a multi-size Windows
 * .ico, theme-aware tray icons, and the splash screen.
 *
 * Usage: npm run assets
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import pngToIco from "png-to-ico";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..");
const LOGO = join(ROOT, "design", "logo");
const OUT = join(ROOT, "design", "exports");
mkdirSync(OUT, { recursive: true });

const ICON_SIZES = [16, 32, 64, 128, 256, 512, 1024];
const ICO_SIZES = [16, 32, 64, 128, 256];

async function renderPng(svgPath, size, outName, { height } = {}) {
  const buf = await sharp(svgPath, { density: 300 })
    .resize(size, height ?? size)
    .png()
    .toBuffer();
  writeFileSync(join(OUT, outName), buf);
  return buf;
}

// Tray icons come from the flat marks (Windows tray is ~16px; the faceted
// gradient turns to mud there, the silhouette stays crisp).
async function trayIcon(svgPath, size, outName) {
  await renderPng(svgPath, size, outName);
}

const appicon = join(LOGO, "corvus-appicon.svg");
const markLight = join(LOGO, "corvus-mark-light.svg");
const markDark = join(LOGO, "corvus-mark-dark.svg");

const icoBuffers = [];
for (const size of ICON_SIZES) {
  const buf = await renderPng(appicon, size, `icon-${size}.png`);
  if (ICO_SIZES.includes(size)) icoBuffers.push(buf);
}
writeFileSync(join(OUT, "corvus.ico"), await pngToIco(icoBuffers));

await trayIcon(markLight, 16, "tray-light-16.png");
await trayIcon(markLight, 32, "tray-light-32.png");
await trayIcon(markDark, 16, "tray-dark-16.png");
await trayIcon(markDark, 32, "tray-dark-32.png");

await renderPng(join(LOGO, "corvus-splash.svg"), 1600, "splash-1600x900.png", { height: 900 });
await renderPng(join(LOGO, "corvus-lockup.svg"), 1120, "lockup-1120x320.png", { height: 320 });
await renderPng(join(LOGO, "corvus-mark.svg"), 512, "social-512.png");

console.log(`Corvus assets exported to ${OUT}`);
