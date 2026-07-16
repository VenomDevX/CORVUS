import { useCallback, useEffect, useState } from "react";
import { api, type ProviderInfo } from "../lib/api";
import { useCorvus } from "../state/store";
import { Select } from "./ui/Select";

/** AI provider + model selection with encrypted per-provider API keys.
 * Providers other than local Ollama need a key, stored via Windows DPAPI. */
export function ProviderSettings() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [active, setActive] = useState("ollama");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [keyInput, setKeyInput] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [provs, settings] = await Promise.all([api.listProviders(), api.getSettings()]);
    setProviders(provs);
    setActive(settings.provider);
    setModel(settings.model ?? "");
    try {
      setModels((await api.listModels()).models);
    } catch {
      setModels([]);
    }
  }, []);

  useEffect(() => {
    if (backendOnline) void load();
  }, [backendOnline, load]);

  const current = providers.find((p) => p.name === active);
  const needsKey = current?.needs_key && !current?.has_key;

  async function switchProvider(name: string) {
    setActive(name);
    setBusy(true);
    try {
      const s = await api.updateSettings({ provider: name });
      setModel(s.model ?? "");
      setModels((await api.listModels()).models);
    } catch {
      setModels([]);
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    if (!keyInput.trim()) return;
    setBusy(true);
    try {
      await api.setProviderKey(active, keyInput.trim());
      setKeyInput("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function clearKey() {
    setBusy(true);
    try {
      await api.clearProviderKey(active);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function changeModel(next: string) {
    setModel(next);
    await api.updateSettings({ model: next });
  }

  if (!backendOnline) {
    return <p className="text-body text-danger">Corvus core is offline — providers unavailable.</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-body-sm text-fg-muted">Provider</label>
        <Select
          className="w-72"
          ariaLabel="Provider"
          value={active}
          disabled={busy}
          onChange={(next) => void switchProvider(next)}
          options={providers.map((p) => ({
            value: p.name,
            label: p.label,
            hint: p.needs_key && !p.has_key ? "key needed" : undefined,
          }))}
        />
      </div>

      {current?.needs_key && (
        <div className="rounded border border-white/10 bg-surface/50 p-3">
          <div className="mb-2 flex items-center gap-2 text-body-sm">
            <span className={`h-2 w-2 rounded-full ${current.has_key ? "bg-success" : "bg-warning"}`} />
            <span className="text-fg-muted">
              {current.has_key ? "API key stored (encrypted)" : "No API key stored"}
            </span>
            {current.key_url && (
              <a
                href={current.key_url}
                onClick={(e) => {
                  e.preventDefault();
                  void window.corvus?.openExternal(current.key_url);
                }}
                className="text-accent-bright underline"
              >
                Get a key
              </a>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder={current.has_key ? "Replace key…" : "Paste API key"}
              aria-label={`${current.label} API key`}
              className="flex-1 rounded border border-white/10 bg-surface px-3 py-2 text-body text-fg outline-none focus:border-accent"
            />
            <button
              onClick={() => void saveKey()}
              disabled={busy || !keyInput.trim()}
              className="rounded bg-accent px-3 py-2 text-body text-white transition-colors duration-fast enabled:hover:bg-accent-bright disabled:opacity-40"
            >
              Save
            </button>
            {current.has_key && (
              <button
                onClick={() => void clearKey()}
                disabled={busy}
                className="rounded bg-white/10 px-3 py-2 text-body text-fg transition-colors duration-fast hover:bg-danger/20 hover:text-danger"
              >
                Remove
              </button>
            )}
          </div>
          <p className="mt-2 text-caption text-fg-faint">
            Keys are encrypted at rest with Windows DPAPI and never leave this machine except to the
            provider you chose.
          </p>
        </div>
      )}

      <div>
        <label className="mb-1 block text-body-sm text-fg-muted" htmlFor="model">
          Model
        </label>
        {needsKey ? (
          <p className="text-body-sm text-warning">Add an API key to load {current?.label} models.</p>
        ) : models.length > 0 ? (
          <Select
            className="w-72"
            ariaLabel="Model"
            value={model}
            onChange={(next) => void changeModel(next)}
            options={(models.includes(model) ? models : [model, ...models])
              .filter(Boolean)
              .map((m) => ({ value: m }))}
          />
        ) : (
          <input
            id="model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            onBlur={() => void changeModel(model)}
            placeholder="model id"
            className="w-72 rounded border border-white/10 bg-surface px-3 py-2 text-body text-fg outline-none focus:border-accent"
          />
        )}
      </div>
    </div>
  );
}
