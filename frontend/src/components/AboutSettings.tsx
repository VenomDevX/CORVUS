import { useEffect, useState } from "react";
import type { UpdateStatus } from "../../electron/preload";

/** Version + auto-update controls. Updates work in the packaged app (against
 * the configured release feed); in dev, checking reports "up to date". */
export function AboutSettings() {
  const [version, setVersion] = useState("");
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    void window.corvus?.getVersion().then(setVersion);
    const off = window.corvus?.onUpdateStatus(setStatus);
    return () => off?.();
  }, []);

  async function check() {
    setChecking(true);
    const result = (await window.corvus?.checkForUpdates()) as UpdateStatus | undefined;
    if (result) setStatus(result);
    setTimeout(() => setChecking(false), 1500);
  }

  const statusText = (): string => {
    if (!status) return "";
    switch (status.state) {
      case "checking": return "Checking for updates…";
      case "available": return `Update ${status.version} available — downloading…`;
      case "downloading": return `Downloading update… ${status.percent}%`;
      case "downloaded": return `Update ${status.version} ready.`;
      case "none": return "Corvus is up to date.";
      case "error": return `Update check failed: ${status.message}`;
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <img src="./logo.png" alt="" className="h-10 w-10" />
        <div>
          <div className="text-body font-semibold text-fg">Corvus</div>
          <div className="text-caption text-fg-faint">Version {version || "—"}</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => void check()}
          disabled={checking}
          className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30 disabled:opacity-50"
        >
          {checking ? "Checking…" : "Check for updates"}
        </button>
        {status?.state === "downloaded" && (
          <button
            onClick={() => void window.corvus?.installUpdate()}
            className="rounded bg-accent px-3 py-1.5 text-body-sm text-white transition-colors duration-fast hover:bg-accent-bright"
          >
            Restart &amp; install
          </button>
        )}
        {statusText() && <span className="text-body-sm text-fg-muted">{statusText()}</span>}
      </div>
    </div>
  );
}
