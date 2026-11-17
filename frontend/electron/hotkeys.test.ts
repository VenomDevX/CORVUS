// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

vi.mock("electron", () => ({ globalShortcut: {} }));
vi.mock("./backend-launcher", () => ({ backendPort: vi.fn(), backendUrl: vi.fn() }));

const { hotkeyChanges, wantedHotkeys } = await import("./hotkeys");

const wf = (name: string, keys: string, extra = {}) => ({
  name, trigger_type: "hotkey", trigger_config: { keys }, enabled: true, ...extra,
});

describe("hotkey sync", () => {
  it("keeps only enabled hotkey workflows", () => {
    const wanted = wantedHotkeys([
      wf("a", "Ctrl+Alt+A"),
      wf("off", "Ctrl+Alt+B", { enabled: false }),
      { name: "s", trigger_type: "schedule", trigger_config: {}, enabled: true },
    ]);
    expect([...wanted]).toEqual([["Ctrl+Alt+A", "a"]]);
  });

  it("adds new keys, drops removed ones, re-registers a key moved to another workflow", () => {
    const current = new Map([["Ctrl+Alt+A", "a"], ["Ctrl+Alt+B", "b"], ["Ctrl+Alt+C", "c"]]);
    const wanted = new Map([["Ctrl+Alt+A", "a"], ["Ctrl+Alt+C", "other"], ["Ctrl+Alt+D", "d"]]);
    expect(hotkeyChanges(current, wanted)).toEqual({
      remove: ["Ctrl+Alt+B", "Ctrl+Alt+C"],
      add: [["Ctrl+Alt+C", "other"], ["Ctrl+Alt+D", "d"]],
    });
  });
});
