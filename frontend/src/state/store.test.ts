import { describe, expect, it } from "vitest";
import { orbStateFor } from "./store";

describe("orb state machine", () => {
  it("is idle when nothing is happening", () => {
    expect(orbStateFor({ generating: false, listening: false, speaking: false })).toBe("idle");
  });

  it("thinks while generating text", () => {
    expect(orbStateFor({ generating: true, listening: false, speaking: false })).toBe("thinking");
  });

  it("voice states outrank generation (Milestone 5 wiring)", () => {
    expect(orbStateFor({ generating: true, listening: true, speaking: false })).toBe("listening");
    expect(orbStateFor({ generating: true, listening: true, speaking: true })).toBe("speaking");
  });
});
