import { useState } from "react";
import { api } from "../lib/api";

/** Install a plugin .zip (manifest.json + plugin.py) via a native file
 * picker in the main process. The plugin arrives disabled — enabling and
 * granting permissions stays a separate, explicit consent step on its card. */
export function AddPluginButton({ onInstalled }: { onInstalled: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function install() {
    setBusy(true);
    setError("");
    try {
      if (await api.installPlugin()) onInstalled();
    } catch (e) {
      const message = e instanceof Error ? e.message : "install failed";
      // ipcRenderer prefixes remote errors; show only the backend's reason.
      setError(message.replace(/^Error invoking remote method '[^']+': (Error: )?/, ""));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex items-center gap-2">
      {error && <span className="max-w-64 truncate text-caption text-danger">{error}</span>}
      <button
        onClick={() => void install()}
        disabled={busy}
        className="rounded bg-accent px-3 py-1.5 text-body-sm text-accent-fg transition-colors duration-fast hover:bg-accent-bright disabled:opacity-50"
      >
        {busy ? "Installing…" : "Add plugin"}
      </button>
    </span>
  );
}
