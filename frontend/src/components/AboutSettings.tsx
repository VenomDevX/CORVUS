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
    <div className="flex flex-col items-center text-center space-y-6 pt-12">
      <div className="flex flex-col items-center gap-3">
        <img src="./logo.png" alt="Corvus Logo" className="h-16 w-16 mb-2" />
        <div>
          <h1 className="text-display font-semibold text-fg">Corvus</h1>
          <div className="text-body text-fg-faint mt-1">Version {version || "—"}</div>
        </div>
      </div>

      <div className="max-w-md text-body text-fg-muted space-y-4">
        <p>
          Corvus is a highly capable, offline-first personal AI assistant. 
          It runs entirely on your local machine, ensuring your data, memories, 
          and documents never leave your device without your explicit permission.
        </p>
        <p>
          By bridging lightweight local LLMs with optional cloud models, 
          Corvus gives you the flexibility of infinite memory and blazing-fast 
          voice interactions without sacrificing privacy.
        </p>
      </div>

      <div className="flex flex-col items-center gap-3 pt-4">
        <button
          onClick={() => void check()}
          disabled={checking}
          className="rounded-full bg-white/10 px-5 py-2 text-body-sm text-fg transition-colors duration-fast hover:bg-white/20 disabled:opacity-50"
        >
          {checking ? "Checking…" : "Check for updates"}
        </button>
        {status?.state === "downloaded" && (
          <button
            onClick={() => void window.corvus?.installUpdate()}
            className="rounded-full bg-white/20 px-5 py-2 text-body-sm text-fg transition-colors duration-fast hover:bg-white/30 mt-2"
          >
            Restart &amp; install
          </button>
        )}
        {statusText() && <span className="text-caption text-fg-faint">{statusText()}</span>}
      </div>

      <div className="pt-8 border-t border-white/5 w-full max-w-sm flex flex-col items-center gap-2">
        <div className="text-caption text-fg-faint">
          Built with <span className="text-fg">React</span>, <span className="text-fg">Electron</span>, and <span className="text-fg">FastAPI</span>.
        </div>
        <div className="text-caption text-fg-faint">
          <a 
            href="#" 
            onClick={(e) => {
              e.preventDefault();
              window.corvus?.openExternal("https://github.com/corvus-ai/corvus");
            }}
            className="text-fg hover:underline transition-all"
          >
            View on GitHub
          </a>
        </div>
      </div>
    </div>
  );
}
