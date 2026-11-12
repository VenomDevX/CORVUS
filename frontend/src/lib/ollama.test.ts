import { afterEach, describe, expect, it, vi } from "vitest";
import { ipcErrorMessage, pullOllamaModel } from "./ollama";

afterEach(() => vi.unstubAllGlobals());

describe("ollama errors", () => {
  it("strips Electron's IPC wrapper", () => {
    const err = new Error("Error invoking remote method 'corvus:install-ollama': Error: Couldn't download Ollama.");
    expect(ipcErrorMessage(err, "x")).toBe("Couldn't download Ollama.");
    expect(ipcErrorMessage("nope", "fallback")).toBe("fallback");
  });

  it("says Ollama isn't running when localhost refuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(pullOllamaModel("m", () => {})).rejects.toThrow("Ollama isn't running");
  });

  it("fails a pull whose stream ends without success", async () => {
    const body = new Response('{"status":"downloading"}\n').body;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    await expect(pullOllamaModel("m", () => {})).rejects.toThrow("stopped before finishing");
  });
});
