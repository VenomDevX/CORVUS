import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { api, type BrowserStatus, type DownloadItem } from "../lib/api";
import { useCorvus } from "../state/store";

/** Downloads section: files Corvus has saved via browser automation, plus the
 * browser session status and the sites you've consented to log in to. */
export function DownloadsView() {
  const [items, setItems] = useState<DownloadItem[]>([]);
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => {
    const [d, s] = await Promise.all([api.downloads(), api.browserStatus()]);
    setItems(d);
    setStatus(s);
  }, []);

  useEffect(() => {
    if (!backendOnline) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [backendOnline, refresh]);

  return (
    <SectionShell
      title="Downloads"
      actions={
        <button
          onClick={() => void refresh()}
          className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
        >
          Refresh
        </button>
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-2 text-body-sm">
        <span className={`h-2 w-2 rounded-full ${status?.open ? "bg-success" : "bg-fg-faint"}`} />
        <span className="text-fg-muted">
          Browser {status?.open ? "session active" : status?.available ? "idle" : "unavailable"}
        </span>
        {status?.consented_sites && status.consented_sites.length > 0 && (
          <span className="text-fg-faint">
            · Signed-in sites: {status.consented_sites.join(", ")}
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="text-body text-fg-muted">
          Nothing downloaded yet. When Corvus downloads a file while browsing, it appears here.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((d, i) => (
            <li key={`${d.path}-${i}`} className="glass flex items-center gap-3 rounded p-3">
              <span className="text-h3" aria-hidden>
                📥
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-body text-fg">{d.filename}</div>
                <div className="truncate text-caption text-fg-faint">from {d.url}</div>
              </div>
              <div className="text-caption text-fg-faint">
                {new Date(d.created_at).toLocaleString()}
              </div>
              <button
                onClick={() => void window.corvus?.openPath(d.path)}
                className="rounded px-2 py-1 text-caption text-accent-bright transition-colors duration-fast hover:bg-accent/10"
              >
                Open
              </button>
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}
