// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  contentSecurityPolicy,
  expectedHandshake,
  isAllowedNavigation,
  resolveOpenablePath,
  verifyBackend,
} from "./guards";

const INDEX = "C:\\Program Files\\Corvus\\resources\\app\\dist\\index.html";

describe("isAllowedNavigation", () => {
  it("packaged: allows only the bundled index.html", () => {
    expect(isAllowedNavigation("file:///C:/Program%20Files/Corvus/resources/app/dist/index.html", null, INDEX)).toBe(true);
    expect(isAllowedNavigation("file:///C:/Program%20Files/Corvus/resources/app/dist/index.html#/widget", null, INDEX)).toBe(true);
  });

  it("packaged: rejects other local pages, UNC shares and the web", () => {
    for (const url of [
      "file:///C:/Users/me/AppData/Local/Corvus/downloads/evil.html",
      "file:///C:/Program%20Files/Corvus/resources/app/dist/../../evil.html",
      "file://attacker-host/share/index.html",
      "https://evil.example/",
      "not a url",
    ]) {
      expect(isAllowedNavigation(url, null, INDEX), url).toBe(false);
    }
  });

  it("dev: same origin only, never a prefix match", () => {
    const dev = "http://127.0.0.1:5173";
    expect(isAllowedNavigation("http://127.0.0.1:5173/#/widget", dev, INDEX)).toBe(true);
    expect(isAllowedNavigation("http://127.0.0.1:5173.evil.com/", dev, INDEX)).toBe(false);
    expect(isAllowedNavigation("http://127.0.0.1:5174/", dev, INDEX)).toBe(false);
  });
});

describe("resolveOpenablePath", () => {
  const base = "C:\\Users\\me\\AppData\\Local\\Corvus";

  it("opens documents inside the data dir", () => {
    expect(resolveOpenablePath(`${base}\\downloads\\report.pdf`, base)).toEqual({
      kind: "open",
      path: `${base}\\downloads\\report.pdf`,
    });
  });

  it("only reveals executables and trailing-dot tricks", () => {
    expect(resolveOpenablePath(`${base}\\downloads\\setup.exe`, base).kind).toBe("reveal");
    expect(resolveOpenablePath(`${base}\\downloads\\setup.exe.`, base).kind).toBe("reveal");
    expect(resolveOpenablePath(`${base}\\downloads\\a.hta`, base).kind).toBe("reveal");
  });

  it("blocks traversal and sibling directories", () => {
    expect(resolveOpenablePath(`${base}\\..\\Other\\x.pdf`, base).kind).toBe("blocked");
    expect(resolveOpenablePath(`${base}Evil\\x.pdf`, base).kind).toBe("blocked");
    expect(resolveOpenablePath("C:\\Windows\\System32\\calc.exe", base).kind).toBe("blocked");
    expect(resolveOpenablePath(`${base.toUpperCase()}\\DOWNLOADS\\X.PDF`, base).kind).toBe("open");
  });
});

describe("verifyBackend (port-squatting defense)", () => {
  const token = "t".repeat(64);
  const nonce = "n".repeat(32);
  const reply = (body: unknown, ok = true) =>
    (async () => ({ ok, json: async () => body })) as unknown as typeof fetch;

  it("accepts a listener that proves it holds the token", async () => {
    expect(await verifyBackend("http://127.0.0.1:1", token, nonce, reply({ hmac: expectedHandshake(token, nonce) }))).toBe(true);
  });

  it("rejects a fake listener", async () => {
    expect(await verifyBackend("http://127.0.0.1:1", token, nonce, reply({ hmac: "00" }))).toBe(false);
    expect(await verifyBackend("http://127.0.0.1:1", token, nonce, reply({ status: "ok" }))).toBe(false);
    expect(await verifyBackend("http://127.0.0.1:1", token, nonce, reply({}, false))).toBe(false);
    const boom = (async () => {
      throw new Error("refused");
    }) as unknown as typeof fetch;
    expect(await verifyBackend("http://127.0.0.1:1", token, nonce, boom)).toBe(false);
  });
});

describe("contentSecurityPolicy", () => {
  it("drops dev-server origins in production", () => {
    expect(contentSecurityPolicy(false)).not.toContain("5173");
    expect(contentSecurityPolicy(true)).toContain("ws://localhost:5173");
    expect(contentSecurityPolicy(false)).toContain("script-src 'self'");
  });
});
