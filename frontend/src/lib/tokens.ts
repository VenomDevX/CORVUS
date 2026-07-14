/**
 * Bridge from design/tokens.json (single source of truth) to typed values the
 * renderer and Tailwind theme consume. Never hardcode hex values in
 * components — extend this module instead.
 */
import tokens from "../../../design/tokens.json";

export const color = tokens.color;
export const typography = tokens.typography;
export const spacing = tokens.spacing;
export const radius = tokens.radius;
export const elevation = tokens.elevation;
export const motion = tokens.motion;

/** Flattened color map for the Tailwind theme (dot keys → nested config). */
export function tailwindColors() {
  return {
    "bg-deep": color.bg["deep-black"],
    "bg-midnight": color.bg["midnight-blue"],
    surface: color.bg.surface,
    "surface-raised": color.bg["surface-raised"],
    accent: color.accent["electric-blue"],
    "accent-bright": color.accent.bright,
    "accent-dim": color.accent.dim,
    "accent-deep": color.accent.deep,
    fg: color.fg.white,
    "fg-muted": color.fg.muted,
    "fg-faint": color.fg.faint,
    success: color.semantic.success,
    warning: color.semantic.warning,
    danger: color.semantic.danger,
    "light-bg": color.light.bg.base,
    "light-surface": color.light.bg.surface,
    "light-surface-raised": color.light.bg["surface-raised"],
    "light-fg": color.light.fg.primary,
    "light-fg-muted": color.light.fg.muted,
    "light-fg-faint": color.light.fg.faint,
  } as const;
}

export type OrbState = "idle" | "listening" | "thinking" | "speaking";
export const ORB_STATES: OrbState[] = ["idle", "listening", "thinking", "speaking"];
