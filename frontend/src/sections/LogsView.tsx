import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { api, type LogEntry } from "../lib/api";
import { useCorvus } from "../state/store";

const LEVEL_COLOR: Record<string, string> = {
  error: "text-danger",
  warning: "text-warning",
  info: "text-fg-muted",
  debug: "text-fg-faint",
};

export function LogsView() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setEntries(await api.tailLogs(300)), []);

  useEffect(() => {
    if (!backendOnline) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [backendOnline, refresh]);

  return (
    <SectionShell
      title="Logs"
      actions={
        <button
          onClick={() => void refresh()}
          className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
        >
          Refresh
        </button>
      }
    >
      <p className="mb-3 text-body-sm text-fg-muted">
        Structured log tail; the full file is at %LOCALAPPDATA%\Corvus\logs\corvus.log.
      </p>
      <div className="glass rounded-lg p-3 font-mono text-mono">
        {entries.length === 0 ? (
          <p className="text-fg-faint">No log entries yet.</p>
        ) : (
          entries.map((e, i) => (
            <div key={i} className="whitespace-pre-wrap break-all py-0.5">
              <span className="text-fg-faint">{e.timestamp}</span>{" "}
              <span className={LEVEL_COLOR[e.level] ?? "text-fg-muted"}>[{e.level}]</span>{" "}
              <span className="text-fg">{e.event}</span>
              {Object.entries(e)
                .filter(([k]) => !["timestamp", "level", "event"].includes(k))
                .map(([k, v]) => (
                  <span key={k} className="text-fg-muted">
                    {" "}
                    {k}={JSON.stringify(v)}
                  </span>
                ))}
            </div>
          ))
        )}
      </div>
    </SectionShell>
  );
}
