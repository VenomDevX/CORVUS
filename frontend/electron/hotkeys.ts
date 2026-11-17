import { globalShortcut } from "electron";
import { backendPort, backendUrl } from "./backend-launcher";

/** Global shortcuts for hotkey-triggered workflows. The backend stores and
 * validates them (two of Ctrl/Alt/Shift + a key); this process owns the
 * OS-level registration and asks the backend to run the workflow on press. */

// ponytail: polls the workflow list; a hotkey created in chat works within
// SYNC_MS. Push a change event from the backend if that lag matters.
const SYNC_MS = 15_000;

type HotkeyWorkflow = {
  name: string;
  trigger_type: string;
  trigger_config: { keys?: string };
  enabled: boolean;
};

/** accelerator -> workflow name */
export type HotkeyMap = Map<string, string>;

export function wantedHotkeys(workflows: HotkeyWorkflow[]): HotkeyMap {
  return new Map(
    workflows
      .filter((w) => w.enabled && w.trigger_type === "hotkey" && w.trigger_config.keys)
      .map((w) => [w.trigger_config.keys as string, w.name]),
  );
}

/** What to unregister and register to turn `current` into `wanted`. A key
 * whose workflow changed is in both lists (its callback captures the name). */
export function hotkeyChanges(current: HotkeyMap, wanted: HotkeyMap) {
  return {
    remove: [...current].filter(([keys, name]) => wanted.get(keys) !== name).map(([keys]) => keys),
    add: [...wanted].filter(([keys, name]) => current.get(keys) !== name),
  };
}

export function startHotkeySync(token: string): void {
  const registered: HotkeyMap = new Map();
  const warned = new Set<string>();
  const headers = { "X-Corvus-Token": token };

  async function run(name: string) {
    await backendPort(); // never send the token to a port mid-restart
    try {
      await fetch(`${backendUrl()}/workflows/${encodeURIComponent(name)}/run`, { method: "POST", headers });
    } catch (err) {
      console.error(`[Corvus] hotkey workflow "${name}" failed to start: ${String(err)}`);
    }
  }

  async function sync() {
    await backendPort();
    let wanted: HotkeyMap;
    try {
      const res = await fetch(`${backendUrl()}/workflows`, { headers });
      if (!res.ok) return;
      wanted = wantedHotkeys((await res.json()) as HotkeyWorkflow[]);
    } catch {
      return; // backend restarting: keep the current shortcuts, retry next tick
    }
    const { remove, add } = hotkeyChanges(registered, wanted);
    for (const keys of remove) {
      globalShortcut.unregister(keys);
      registered.delete(keys);
    }
    for (const [keys, name] of add) {
      if (globalShortcut.register(keys, () => void run(name))) {
        registered.set(keys, name);
        warned.delete(keys);
      } else if (!warned.has(keys)) {
        warned.add(keys); // retried every tick, logged once
        console.warn(`[Corvus] ${keys} is taken by another app; workflow "${name}" has no hotkey.`);
      }
    }
  }

  void sync();
  setInterval(() => void sync(), SYNC_MS).unref();
}
