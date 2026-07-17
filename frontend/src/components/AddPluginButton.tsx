import { useRef, useState } from "react";
import { api } from "../lib/api";

/** Upload-and-install a plugin .zip (manifest.json + plugin.py). The plugin
 * arrives disabled — enabling and granting permissions stays a separate,
 * explicit consent step on its card. */
export function AddPluginButton({ onInstalled }: { onInstalled: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function install(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await api.installPlugin(file);
      onInstalled();
    } catch (e) {
      setError(e instanceof Error ? e.message : "install failed");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <span className="flex items-center gap-2">
      {error && <span className="max-w-64 truncate text-caption text-danger">{error}</span>}
      <button
        onClick={() => input.current?.click()}
        disabled={busy}
        className="rounded bg-accent px-3 py-1.5 text-body-sm text-white transition-colors duration-fast hover:bg-accent-bright disabled:opacity-50"
      >
        {busy ? "Installing…" : "Add plugin"}
      </button>
      <input
        ref={input}
        type="file"
        accept=".zip,application/zip"
        hidden
        onChange={(e) => void install(e.target.files?.[0])}
      />
    </span>
  );
}
