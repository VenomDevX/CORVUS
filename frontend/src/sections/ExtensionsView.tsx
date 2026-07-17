import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { api, type Plugin } from "../lib/api";
import { useCorvus } from "../state/store";
import { PluginCard } from "../components/PluginCard";
import { AddPluginButton } from "../components/AddPluginButton";

/** Extensions marketplace: browse and enable plugins. New plugins are folders
 * with a manifest.json + plugin.py dropped into %LOCALAPPDATA%\Corvus\plugins. */
export function ExtensionsView() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setPlugins(await api.listPlugins()), []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  return (
    <SectionShell
      title="Extensions"
      actions={
        <span className="flex items-center gap-2">
          <button
            onClick={() => void refresh()}
            className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
          >
            Refresh
          </button>
          <AddPluginButton onInstalled={() => void refresh()} />
        </span>
      }
    >
      <p className="mb-4 text-body-sm text-fg-muted">
        Plugins add new actions Corvus can use. Each declares the permissions it needs; you grant
        them explicitly. Build your own with the plugin SDK — a folder with a{" "}
        <code className="rounded-sm bg-white/10 px-1 font-mono text-mono">manifest.json</code> and a{" "}
        <code className="rounded-sm bg-white/10 px-1 font-mono text-mono">plugin.py</code>.
      </p>
      {plugins.length === 0 ? (
        <p className="text-body text-fg-muted">No plugins found.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {plugins.map((p) => (
            <PluginCard key={p.id} plugin={p} onChange={() => void refresh()} />
          ))}
        </div>
      )}
    </SectionShell>
  );
}
