import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { api, type SystemSpecs } from "../lib/api";
import { pullOllamaModel, type PullProgress } from "../lib/ollama";
import { useCorvus } from "../state/store";

const FIT_LABEL = {
  recommended: { text: "Recommended for your device", cls: "text-success" },
  cpu_ok: { text: "Runs on CPU (slower)", cls: "text-warning" },
  too_big: { text: "Too big for this device", cls: "text-danger" },
} as const;

/** Offline (Ollama) model manager: download curated models in-app, switch the
 * active one. Reuses the first-run wizard's device-fit annotations. */
export function OllamaModels() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [specs, setSpecs] = useState<SystemSpecs | null>(null);
  const [activeModel, setActiveModel] = useState("");
  const [pulling, setPulling] = useState<string | null>(null);
  const [pull, setPull] = useState<PullProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, settings] = await Promise.all([api.systemSpecs(), api.getSettings()]);
    setSpecs(s);
    if (settings.provider === "ollama") setActiveModel(settings.model ?? "");
  }, []);

  useEffect(() => {
    if (backendOnline) void refresh().catch(() => undefined);
  }, [backendOnline, refresh]);

  if (!specs) return <Loader2 className="h-5 w-5 animate-spin text-fg-muted" />;

  if (!specs.ollama.running) {
    return (
      <p className="text-body-sm text-warning">
        Ollama isn't running — start it (or install it from{" "}
        <button
          onClick={() => void window.corvus?.openExternal("https://ollama.com/download")}
          className="text-accent-bright underline"
        >
          ollama.com
        </button>
        ) to manage offline models.
      </p>
    );
  }

  const installed = new Set(specs.ollama.models.map((m) => m.name));
  // Curated catalog first, then anything else the user already has installed.
  const extras = specs.ollama.models.filter((m) => !specs.catalog.some((c) => c.id === m.name));

  async function download(id: string) {
    setPulling(id);
    setPull({ percent: 0, status: "starting" });
    setError(null);
    try {
      await pullOllamaModel(id, setPull);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "download failed");
    } finally {
      setPulling(null);
      setPull(null);
    }
  }

  async function use(id: string) {
    setError(null);
    try {
      await api.updateSettings({ provider: "ollama", model: id });
      setActiveModel(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't switch model");
    }
  }

  function row(id: string, label: string, meta: string, fit?: keyof typeof FIT_LABEL) {
    const isInstalled = installed.has(id);
    const isActive = id === activeModel;
    return (
      <div
        key={id}
        className="flex items-center justify-between gap-3 rounded-lg bg-white/5 px-3 py-2"
      >
        <div className="min-w-0">
          <span className="text-body-sm font-semibold text-fg">
            {label}
            {isActive && (
              <span className="ml-2 rounded-sm bg-accent/25 px-1.5 py-0.5 text-caption text-accent-bright">
                In use
              </span>
            )}
          </span>
          <div className="text-caption text-fg-muted">
            {meta}
            {fit && <span className={`ml-2 ${FIT_LABEL[fit].cls}`}>{FIT_LABEL[fit].text}</span>}
          </div>
        </div>
        <div className="shrink-0">
          {pulling === id ? (
            <span className="flex w-40 items-center gap-2">
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                <span
                  className="block h-full rounded-full bg-accent transition-all duration-base"
                  style={{ width: `${Math.round((pull?.percent ?? 0) * 100)}%` }}
                />
              </span>
              <span className="w-9 text-right text-caption text-fg-muted">
                {Math.round((pull?.percent ?? 0) * 100)}%
              </span>
            </span>
          ) : isInstalled ? (
            <button
              onClick={() => void use(id)}
              disabled={isActive}
              className="rounded bg-white/10 px-3 py-1.5 text-caption text-fg transition-colors duration-fast enabled:hover:bg-accent/25 enabled:hover:text-accent-bright disabled:opacity-50"
            >
              {isActive ? "Active" : "Use"}
            </button>
          ) : (
            <button
              onClick={() => void download(id)}
              disabled={pulling !== null}
              className="flex items-center gap-1.5 rounded bg-white/10 px-3 py-1.5 text-caption text-fg transition-colors duration-fast enabled:hover:bg-accent/25 enabled:hover:text-accent-bright disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5" /> Download
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {specs.catalog.map((m) =>
        row(m.id, m.label, `${m.download_gb} GB · ${m.blurb}`, m.fit),
      )}
      {extras.length > 0 && (
        <>
          <div className="pt-1 text-caption text-fg-faint">Also installed</div>
          {extras.map((m) => row(m.name, m.name, `${m.size_gb} GB`))}
        </>
      )}
      {error && <p className="text-caption text-danger">{error}</p>}
    </div>
  );
}
