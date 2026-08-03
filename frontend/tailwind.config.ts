import type { Config } from "tailwindcss";
import tokens from "../design/tokens.json";

const scale = tokens.typography.scale as Record<
  string,
  { size: string; lineHeight: string; weight: number; tracking: string }
>;

const fontSize = Object.fromEntries(
  Object.entries(scale).map(([name, t]) => [
    name,
    [t.size, { lineHeight: t.lineHeight, letterSpacing: t.tracking, fontWeight: String(t.weight) }],
  ]),
);

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // Theme-dependent semantics — resolved from CSS variables that
        // src/lib/theme.ts writes from design/tokens.json.
        app: "var(--c-bg)",
        "app-secondary": "var(--c-bg-secondary)",
        surface: "var(--c-surface)",
        "surface-raised": "var(--c-surface-raised)",
        fg: "var(--c-fg)",
        "fg-muted": "var(--c-fg-muted)",
        "fg-faint": "var(--c-fg-faint)",
        // Theme-constant brand + semantic colors (hex → opacity modifiers work).
        accent: "rgb(var(--c-accent) / <alpha-value>)",
        "accent-bright": "rgb(var(--c-accent) / <alpha-value>)",
        "accent-fg": "rgb(var(--c-accent-fg) / <alpha-value>)",
        "accent-dim": tokens.color.accent.dim,
        "accent-deep": tokens.color.accent.deep,
        "bg-caviar": tokens.color.bg.caviar,
        "bg-rein": tokens.color.bg.rein,
        success: tokens.color.semantic.success,
        warning: tokens.color.semantic.warning,
        danger: tokens.color.semantic.danger,
      },
      fontFamily: {
        ui: tokens.typography.font.ui.split(",").map((s) => s.trim()),
        mono: tokens.typography.font.mono.split(",").map((s) => s.trim()),
      },
      fontSize: fontSize as Record<string, [string, object]>,
      borderRadius: {
        sm: tokens.radius.sm,
        DEFAULT: tokens.radius.default,
        lg: tokens.radius.lg,
        xl: tokens.radius.xl,
      },
      boxShadow: {
        "glass-1": tokens.elevation["glass-1"],
        "glass-2": tokens.elevation["glass-2"],
        "glass-3": tokens.elevation["glass-3"],
        glow: tokens.elevation["glow-accent"],
        "glow-strong": tokens.elevation["glow-accent-strong"],
      },
      transitionDuration: {
        fast: tokens.motion.duration.fast,
        base: tokens.motion.duration.base,
        slow: tokens.motion.duration.slow,
      },
    },
  },
  plugins: [],
} satisfies Config;
