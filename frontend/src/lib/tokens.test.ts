import { describe, expect, it } from "vitest";
import tokens from "../../../design/tokens.json";
import { ORB_STATES, tailwindColors } from "./tokens";
import config from "../../tailwind.config";

describe("design tokens → Tailwind theme", () => {
  it("exposes the brand palette from tokens.json", () => {
    const colors = tailwindColors();
    expect(colors["bg-caviar"]).toBe(tokens.color.bg.caviar);
    expect(colors.accent).toBe(tokens.color.accent["electric-blue"]);
    expect(colors.fg).toBe(tokens.color.fg.white);
  });

  it("keeps the accent constant across themes in the Tailwind config", () => {
    const themeColors = (config.theme?.extend?.colors ?? {}) as Record<string, string>;
    expect(themeColors.accent).toContain("--c-accent");
    // Semantic neutrals must go through CSS variables so light mode can invert them.
    expect(themeColors.fg).toBe("var(--c-fg)");
    expect(themeColors.surface).toBe("var(--c-surface)");
  });

  it("defines the full type scale", () => {
    for (const step of ["display", "h1", "h2", "h3", "h4", "body", "body-sm", "caption", "mono"]) {
      expect(tokens.typography.scale).toHaveProperty(step);
    }
  });

  it("defines all four orb states with motion specs", () => {
    expect(ORB_STATES).toEqual(["idle", "listening", "thinking", "speaking"]);
    for (const state of ORB_STATES) {
      expect(tokens.motion.orb).toHaveProperty(state);
    }
  });
});
