import { color } from "./tokens";
import type { Theme } from "../state/store";

/**
 * Writes the theme-dependent CSS variables from design/tokens.json onto the
 * document root. Tailwind's semantic colors (fg, surface, …) resolve to these
 * variables, so neutrals invert between themes while the electric-blue accent
 * stays constant (brand rule).
 */
export function applyThemeVars(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;

  const vars: Record<string, string> =
    theme === "dark"
      ? {
          "--c-bg": color.bg["deep-black"],
          "--c-bg-secondary": color.bg["midnight-blue"],
          "--c-surface": color.bg.surface,
          "--c-surface-raised": color.bg["surface-raised"],
          "--c-fg": color.fg.white,
          "--c-fg-muted": color.fg.muted,
          "--c-fg-faint": color.fg.faint,
          "--glass-fill": color.glass.fill,
          "--glass-border": color.glass.border,
        }
      : {
          "--c-bg": color.light.bg.base,
          "--c-bg-secondary": color.light.bg["surface-raised"],
          "--c-surface": color.light.bg.surface,
          "--c-surface-raised": color.light.bg["surface-raised"],
          "--c-fg": color.light.fg.primary,
          "--c-fg-muted": color.light.fg.muted,
          "--c-fg-faint": color.light.fg.faint,
          "--glass-fill": color.light.glass.fill,
          "--glass-border": color.light.glass.border,
        };

  for (const [key, value] of Object.entries(vars)) root.style.setProperty(key, value);

  // Keep the native window buttons legible in both themes.
  void window.corvus?.setTitlebarSymbolColor(theme === "dark" ? color.fg.white : color.light.fg.primary);
}
