import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { Tabs } from "../components/ui/Tabs";
import { api, type Plugin } from "../lib/api";
import { useCorvus } from "../state/store";
import { PluginCard } from "../components/PluginCard";
import { AddPluginButton } from "../components/AddPluginButton";

/** Plugins: installed (enabled, with revocable permission grants) and
 * available (everything found in %LOCALAPPDATA%\Corvus\plugins). */
export function PluginsView() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [tab, setTab] = useState<"installed" | "available">("installed");
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setPlugins(await api.listPlugins()), []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  const enabled = plugins.filter((p) => p.enabled);
  const shown = tab === "installed" ? enabled : plugins.filter((p) => !p.enabled);

  return (
    <SectionShell title="Plugins" actions={<AddPluginButton onInstalled={() => void refresh()} />}>
      <p className="mb-4 text-body-sm text-fg-muted">
        Plugins add new actions Corvus can use. Each asks for the permissions it needs, and you can
        revoke them any time.
      </p>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "installed", label: `Installed (${enabled.length})` },
          { value: "available", label: `Available (${plugins.length - enabled.length})` },
        ]}
      />
      {shown.length === 0 ? (
        <p className="text-body text-fg-muted">
          {tab === "installed"
            ? "No plugins enabled yet. Enable one from Available."
            : "Nothing else to enable. Add a plugin folder with a manifest.json and plugin.py."}
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {shown.map((p) => (
            <PluginCard key={p.id} plugin={p} onChange={() => void refresh()} />
          ))}
        </div>
      )}
    </SectionShell>
  );
}
