import { useCallback, useEffect, useState } from "react";
import { api, type Workflow } from "../lib/api";
import { useCorvus } from "../state/store";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const TRIGGER_LABEL: Record<Workflow["trigger_type"], (w: Workflow) => string> = {
  manual: () => "manual",
  schedule: ({ trigger_config: c }) =>
    `${c.days?.length ? c.days.map((d) => DAYS[d]).join(", ") : "daily"} at ${c.at ?? "?"}`,
  interval: (w) => `every ${w.trigger_config.every_minutes ?? "?"} min`,
  startup: () => "when Corvus starts",
  idle: (w) => `after ${w.trigger_config.minutes ?? "?"} min idle`,
  folder: (w) => `new file in ${w.trigger_config.path ?? "?"}`,
  voice: (w) => `say “${w.trigger_config.phrase ?? "?"}”`,
  hotkey: (w) => `press ${w.trigger_config.keys ?? "?"}`,
};

/** Saved workflows: run or delete them here. Create new ones by asking Corvus
 * in chat ("make a morning routine that opens Chrome and Spotify"). */
export function WorkflowsPanel() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setWorkflows(await api.listWorkflows()), []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  async function run(name: string) {
    setRunning(name);
    try {
      await api.runWorkflow(name);
    } finally {
      setRunning(null);
    }
  }

  async function remove(name: string) {
    await api.deleteWorkflow(name);
    await refresh();
  }

  return (
    <section className="mb-6">
      <h2 className="mb-1 text-h4">Workflows</h2>
      <p className="mb-3 text-body-sm text-fg-muted">
        Multi-step routines. Ask Corvus in chat to create one — e.g. “make a workflow called morning
        that opens Chrome and Spotify.” Run it here, by voice, on a schedule, every few minutes, when Corvus starts, when you step away,
        when a new file lands in a folder, or with a keyboard shortcut.
      </p>
      {workflows.length === 0 ? (
        <p className="text-body text-fg-muted">No workflows yet.</p>
      ) : (
        <ul className="space-y-2">
          {workflows.map((w) => (
            <li key={w.id} className="glass rounded-lg p-3">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-body font-semibold text-fg">{w.name}</span>
                    <span className="rounded-sm bg-accent/15 px-1.5 py-0.5 text-caption text-accent-bright">
                      {TRIGGER_LABEL[w.trigger_type](w)}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-caption text-fg-faint">
                    {w.steps.map((s) => s.action).join(" → ")}
                  </div>
                </div>
                <button
                  onClick={() => void run(w.name)}
                  disabled={running === w.name}
                  className="rounded bg-accent px-3 py-1.5 text-body-sm text-white transition-colors duration-fast enabled:hover:bg-accent-bright disabled:opacity-50"
                >
                  {running === w.name ? "Running…" : "▶ Run"}
                </button>
                <button
                  onClick={() => void remove(w.name)}
                  aria-label={`Delete workflow ${w.name}`}
                  className="rounded px-2 py-1.5 text-caption text-fg-faint transition-colors duration-fast hover:bg-danger/20 hover:text-danger"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
