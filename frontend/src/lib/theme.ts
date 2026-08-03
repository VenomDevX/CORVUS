import { color, typography } from "./tokens";
import type { Theme } from "../state/store";

/**
 * Writes the theme-dependent CSS variables from design/tokens.json onto the
 * document root. Tailwind's semantic colors (fg, surface, …) resolve to these
 * variables, so neutrals invert between themes while the electric-blue accent
 * stays constant (brand rule).
 */
export function applyThemeVars(state: {
  theme: Theme;
  accentColor: string;
  fontFamily: string;
  uiRoundness: string;
  appOpacity: string;
  animationSpeed: string;
  uiScale: string;
}) {
  const root = document.documentElement;
  root.dataset.theme = state.theme;

  const getAccentHex = (accent: string) => {
    switch (accent) {
      case "blue": return "59 130 246";       // #3B82F6
      case "emerald": return "16 185 129";    // #10B981
      case "amethyst": return "139 92 246";   // #8B5CF6
      case "amber": return "245 158 11";      // #F59E0B
      case "ruby": return "239 68 68";        // #EF4444
      case "ocean": return "6 182 212";       // #06B6D4
      case "cyberpunk": return "244 114 182"; // #F472B6
      case "forest": return "5 150 105";      // #059669
      case "blush": return "254 205 211";     // #FECDD3
      case "neon": return "57 255 20";        // #39FF14
      case "midnight": return "30 58 138";    // #1E3A8A
      case "black": return "0 0 0";           // #000000
      case "monochrome":
      default:
        switch (state.theme) {
          case "pink": return "131 24 67"; // #831843
          case "green": return "236 253 245"; // #ECFDF5
          case "blue": return "248 250 252"; // #F8FAFC
          case "purple": return "245 243 255"; // #F5F3FF
          case "dark": return "255 255 255"; // white
          case "light":
          default: return "11 18 32"; // #0B1220
        }
    }
  };

  const getAccentFgHex = (accent: string) => {
    switch (accent) {
      case "amber":
      case "blush":
      case "neon":
      case "cyberpunk":
        return "0 0 0"; // black text on bright accents
      case "monochrome":
        switch (state.theme) {
          case "pink":
          case "light":
            return "255 255 255"; // dark button -> white text
          case "green":
          case "blue":
          case "purple":
          case "dark":
          default:
            return "0 0 0"; // light button -> black text
        }
      default:
        return "255 255 255"; // white text on blue, ruby, emerald, etc
    }
  };

  const getFontFamily = (font: string) => {
    switch (font) {
      case "monospace": return typography?.font?.mono ?? "'JetBrains Mono', monospace";
      case "serif": return "Georgia, 'Times New Roman', serif";
      case "comic": return "'Comic Sans MS', 'Chalkboard SE', 'Marker Felt', sans-serif";
      case "system":
      default:
        return typography?.font?.ui ?? "Inter, system-ui, sans-serif";
    }
  };

  const getRoundness = (roundness: string) => {
    switch (roundness) {
      case "sharp": return "0px";
      case "rounded": return "12px";
      case "pill": return "9999px";
      case "default":
      default:
        return "6px";
    }
  };

  const getOpacity = (opacity: string) => {
    switch (opacity) {
      case "solid": return "1.0";
      case "transparent": return "0.4";
      case "glassy":
      default:
        return "0.75";
    }
  };

  const getUiScale = (scale: string) => {
    switch (scale) {
      case "compact": return "14px";
      case "large": return "18px";
      case "default":
      default: return "16px";
    }
  };

  const getAnimationSpeed = (speed: string) => {
    switch (speed) {
      case "fast": return "100ms";
      case "slow": return "400ms";
      case "default":
      default: return "200ms";
    }
  };

  let baseVars: Record<string, string>;
  if (state.theme === "dark") {
    baseVars = {
      "--c-bg": color.bg.caviar,
      "--c-bg-secondary": color.bg.rein,
      "--c-surface": color.bg.shadow,
      "--c-surface-raised": color.bg.saddle,
      "--c-fg": color.fg.white,
      "--c-fg-muted": color.fg.muted,
      "--c-fg-faint": color.fg.faint,
      "--glass-fill": `rgba(49, 46, 46, ${getOpacity(state.appOpacity)})`,
      "--glass-border": color.glass.border,
    };
  } else if (state.theme === "pink") {
    baseVars = {
      "--c-bg": "#FDF2F8",
      "--c-bg-secondary": "#FCE7F3",
      "--c-surface": "#FBCFE8",
      "--c-surface-raised": "#F9A8D4",
      "--c-fg": "#831843",
      "--c-fg-muted": "#9D174D",
      "--c-fg-faint": "#BE185D",
      "--glass-fill": `rgba(253, 242, 248, ${getOpacity(state.appOpacity)})`,
      "--glass-border": "rgba(131, 24, 67, 0.15)",
    };
  } else if (state.theme === "green") {
    baseVars = {
      "--c-bg": "#022C22",
      "--c-bg-secondary": "#064E3B",
      "--c-surface": "#065F46",
      "--c-surface-raised": "#047857",
      "--c-fg": "#ECFDF5",
      "--c-fg-muted": "#A7F3D0",
      "--c-fg-faint": "#6EE7B7",
      "--glass-fill": `rgba(2, 44, 34, ${getOpacity(state.appOpacity)})`,
      "--glass-border": "rgba(236, 253, 245, 0.15)",
    };
  } else if (state.theme === "blue") {
    baseVars = {
      "--c-bg": "#020617",
      "--c-bg-secondary": "#0F172A",
      "--c-surface": "#1E293B",
      "--c-surface-raised": "#334155",
      "--c-fg": "#F8FAFC",
      "--c-fg-muted": "#CBD5E1",
      "--c-fg-faint": "#94A3B8",
      "--glass-fill": `rgba(2, 6, 23, ${getOpacity(state.appOpacity)})`,
      "--glass-border": "rgba(248, 250, 252, 0.15)",
    };
  } else if (state.theme === "purple") {
    baseVars = {
      "--c-bg": "#170824",
      "--c-bg-secondary": "#210B38",
      "--c-surface": "#2E104F",
      "--c-surface-raised": "#3B0764",
      "--c-fg": "#F5F3FF",
      "--c-fg-muted": "#DDD6FE",
      "--c-fg-faint": "#A78BFA",
      "--glass-fill": `rgba(23, 8, 36, ${getOpacity(state.appOpacity)})`,
      "--glass-border": "rgba(245, 243, 255, 0.15)",
    };
  } else {
    // Light
    baseVars = {
      "--c-bg": color.light.bg.base,
      "--c-bg-secondary": color.light.bg["surface-raised"],
      "--c-surface": color.light.bg.surface,
      "--c-surface-raised": color.light.bg["surface-raised"],
      "--c-fg": color.light.fg.primary,
      "--c-fg-muted": color.light.fg.muted,
      "--c-fg-faint": color.light.fg.faint,
      "--glass-fill": `rgba(255, 255, 255, ${getOpacity(state.appOpacity)})`,
      "--glass-border": color.light.glass.border,
    };
  }

  const extraVars = {
    "--c-accent": getAccentHex(state.accentColor),
    "--c-accent-fg": getAccentFgHex(state.accentColor),
    "--font-family": getFontFamily(state.fontFamily),
    "--ui-roundness": getRoundness(state.uiRoundness),
    "--animation-speed": getAnimationSpeed(state.animationSpeed),
  };

  const vars = { ...baseVars, ...extraVars };
  for (const [key, value] of Object.entries(vars)) root.style.setProperty(key, value);
  root.style.fontSize = getUiScale(state.uiScale);

  // Keep the native window buttons legible in both themes.
  void window.corvus?.setTitlebarSymbolColor(state.theme === "dark" || state.theme === "blue" || state.theme === "purple" || state.theme === "green" ? color.fg.white : color.light.fg.primary);
}
