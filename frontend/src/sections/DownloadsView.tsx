import { useCallback, useEffect, useState } from "react";
import { api, type BrowserStatus, type DownloadItem } from "../lib/api";
import { useCorvus } from "../state/store";

/** Downloads tab (inside Tasks): files Corvus has saved via browser automation, plus the
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
    const tick = () => void refresh().catch(() => undefined); // next tick retries
    tick();
    const timer = setInterval(tick, 5000);
    return () => clearInterval(timer);
  }, [backendOnline, refresh]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-body-sm">
        <button
          onClick={() => void refresh()}
          className="ml-auto order-last rounded px-2 py-1 text-caption text-fg-muted transition-colors duration-fast hover:bg-white/5 hover:text-fg"
        >
          Refresh
        </button>
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
    </div>
  );
}
