import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { api, type Plugin } from "../lib/api";
import { useCorvus } from "../state/store";
import { PluginCard } from "../components/PluginCard";

/** Plugins management: enabled plugins and their permission grants, revocable
 * here. Browse and install more under Extensions. */
export function PluginsView() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setPlugins(await api.listPlugins()), []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  const enabled = plugins.filter((p) => p.enabled);

  return (
    <SectionShell title="Plugins">
      <p className="mb-4 text-body-sm text-fg-muted">
        Installed plugins and the permissions you&rsquo;ve granted them. Revoke a permission any time —
        the plugin&rsquo;s actions disappear until it&rsquo;s granted again. Add more from Extensions.
      </p>
      {enabled.length === 0 ? (
        <p className="text-body text-fg-muted">
          No plugins enabled. Visit Extensions to enable one.
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {enabled.map((p) => (
            <PluginCard key={p.id} plugin={p} onChange={() => void refresh()} />
          ))}
        </div>
      )}
    </SectionShell>
  );
}
