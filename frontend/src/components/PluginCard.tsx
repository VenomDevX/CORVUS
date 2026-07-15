import { api, type Plugin } from "../lib/api";

/** One plugin: enable/disable, and grant/revoke each declared permission.
 * A plugin only loads (its actions appear) once enabled with all permissions
 * granted — the card makes that state explicit. */
export function PluginCard({ plugin, onChange }: { plugin: Plugin; onChange: () => void }) {
  async function toggleEnabled() {
    if (plugin.enabled) await api.disablePlugin(plugin.id);
    else await api.enablePlugin(plugin.id);
    onChange();
  }

  async function togglePermission(perm: string) {
    const next = plugin.granted_permissions.includes(perm)
      ? plugin.granted_permissions.filter((p) => p !== perm)
      : [...plugin.granted_permissions, perm];
    await api.setPluginPermissions(plugin.id, next);
    onChange();
  }

  const missing = plugin.permissions.filter((p) => !plugin.granted_permissions.includes(p));

  return (
    <div className="glass rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-body font-semibold text-fg">{plugin.name}</span>
            <span className="text-caption text-fg-faint">v{plugin.version}</span>
            {plugin.bundled && (
              <span className="rounded-sm bg-white/5 px-1.5 py-0.5 text-caption text-fg-muted">
                built-in
              </span>
            )}
            {plugin.loaded && (
              <span className="rounded-sm bg-success/15 px-1.5 py-0.5 text-caption text-success">
                active
              </span>
            )}
          </div>
          <p className="mt-1 text-body-sm text-fg-muted">{plugin.description}</p>
          <p className="mt-0.5 text-caption text-fg-faint">by {plugin.author}</p>
        </div>
        <button
          onClick={() => void toggleEnabled()}
          className={`shrink-0 rounded px-3 py-1.5 text-body-sm transition-colors duration-fast ${
            plugin.enabled
              ? "bg-white/10 text-fg hover:bg-danger/20 hover:text-danger"
              : "bg-accent text-white hover:bg-accent-bright"
          }`}
        >
          {plugin.enabled ? "Disable" : "Enable"}
        </button>
      </div>

      {plugin.permissions.length > 0 && (
        <div className="mt-3 border-t border-white/10 pt-3">
          <div className="mb-1 text-caption text-fg-faint">Permissions</div>
          <div className="flex flex-wrap gap-2">
            {plugin.permissions.map((perm) => {
              const granted = plugin.granted_permissions.includes(perm);
              return (
                <button
                  key={perm}
                  onClick={() => void togglePermission(perm)}
                  className={`rounded-sm px-2 py-1 text-caption transition-colors duration-fast ${
                    granted
                      ? "bg-accent/20 text-accent-bright"
                      : "bg-warning/15 text-warning hover:bg-warning/25"
                  }`}
                >
                  {granted ? "✓ " : "○ "}
                  {perm}
                </button>
              );
            })}
          </div>
          {plugin.enabled && missing.length > 0 && (
            <p className="mt-2 text-caption text-warning">
              Grant {missing.join(", ")} to activate this plugin.
            </p>
          )}
        </div>
      )}

      {plugin.error && <p className="mt-2 text-caption text-danger">Error: {plugin.error}</p>}
      {plugin.actions.length > 0 && (
        <p className="mt-2 text-caption text-fg-faint">
          Adds: {plugin.actions.map((a) => a.split(".").slice(1).join(".")).join(", ")}
        </p>
      )}
    </div>
  );
}
