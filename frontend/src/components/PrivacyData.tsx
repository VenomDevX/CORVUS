import { useCallback, useEffect, useRef, useState } from "react";
import { api, type EgressEntry, type Retention } from "../lib/api";
import { useCorvus } from "../state/store";
import { Select } from "./ui/Select";

const RETENTION_OPTIONS = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "0", label: "Keep forever" },
];

const FOLDER_LABEL: Record<keyof Retention, string> = {
  screenshots: "Screenshots (screen reading, page captures)",
  uploads: "Attached files",
  downloads: "Browser downloads",
};

const BUTTON = "rounded px-3 py-1.5 text-body-sm transition-colors duration-fast disabled:opacity-40";

/** Settings → Privacy & Data: what left this computer this session,
 * retention for files Corvus creates, backup/restore, and full wipe. */
export function PrivacyData() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [egress, setEgress] = useState<{ cloud_provider: string | null; entries: EgressEntry[] }>();
  const [retention, setRetention] = useState<Retention>();
  const [passphrase, setPassphrase] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const importInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const [e, r] = await Promise.all([api.egress(), api.retention()]);
    setEgress(e);
    setRetention(r);
  }, []);

  useEffect(() => {
    if (!backendOnline) return;
    void refresh();
    const timer = setInterval(() => void api.egress().then(setEgress), 5000);
    return () => clearInterval(timer);
  }, [backendOnline, refresh]);

  async function run(work: () => Promise<string | null>) {
    setBusy(true);
    setStatus(null);
    try {
      const text = await work();
      if (text) setStatus({ ok: true, text });
    } catch (e) {
      setStatus({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  const exportBackup = () =>
    run(async () => {
      const blob = await api.exportData(passphrase);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `corvus-backup-${new Date().toISOString().slice(0, 10)}.corvusbak`;
      a.click();
      URL.revokeObjectURL(url);
      return "Backup saved. Keep the passphrase - without it the file can't be opened.";
    });

  const importBackup = (file: File | undefined) =>
    run(async () => {
      if (!file) return null;
      const counts = await api.importData(file, passphrase);
      if (importInput.current) importInput.current.value = "";
      return `Imported ${counts.conversations} conversations, ${counts.memories} memories, ${counts.workflows} workflows and ${counts.reminders} reminders.`;
    });

  const wipe = () =>
    run(async () => {
      const result = await api.wipeData();
      return result.cancelled ? null : "Deleting… Corvus will restart with a clean slate.";
    });

  const passphraseOk = passphrase.length >= 8;

  return (
    <>
      <h2 className="mb-2 text-h3 tracking-tight font-medium">Privacy &amp; Data</h2>
      <p className="mb-6 text-body-sm text-fg-muted">
        Corvus is local-first. This page shows what has left this computer and lets you control what
        Corvus keeps.
      </p>

      <section className="mb-8">
        <h3 className="mb-2 text-body font-semibold">Sent off this computer (this session)</h3>
        {egress?.cloud_provider ? (
          <p className="mb-3 text-body-sm text-warning">
            Your active AI provider is {egress.cloud_provider}: chat messages go to its servers. Corvus asks
            before sending your screen, documents, clipboard or files.
          </p>
        ) : (
          <p className="mb-3 text-body-sm text-fg-muted">
            Your AI provider runs locally, so conversations stay on this computer.
          </p>
        )}
        {egress && egress.entries.length > 0 ? (
          <div className="glass max-h-72 overflow-y-auto rounded-lg">
            <table className="w-full text-body-sm">
              <thead className="text-caption text-fg-faint">
                <tr>
                  <th className="px-3 py-2 text-left font-normal">Time</th>
                  <th className="px-3 py-2 text-left font-normal">Sent to</th>
                  <th className="px-3 py-2 text-left font-normal">What</th>
                  <th className="px-3 py-2 text-right font-normal">Size</th>
                </tr>
              </thead>
              <tbody>
                {egress.entries.map((e, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="px-3 py-1.5 text-fg-faint">{new Date(e.time).toLocaleTimeString()}</td>
                    <td className="px-3 py-1.5 text-fg">{e.destination}</td>
                    <td className="px-3 py-1.5 text-fg-muted">
                      {e.kind}
                      {e.contains.length > 0 && (
                        <span className="text-warning"> · includes {e.contains.join(", ")}</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-mono text-fg-faint">
                      {e.chars.toLocaleString()} {e.kind === "image" ? "bytes" : "chars"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-body-sm text-fg-faint">Nothing has been sent off this computer yet.</p>
        )}
      </section>

      <section className="mb-8">
        <h3 className="mb-2 text-body font-semibold">Keep files Corvus creates for</h3>
        {retention &&
          (Object.keys(FOLDER_LABEL) as (keyof Retention)[]).map((folder) => (
            <div key={folder} className="mb-2 flex items-center justify-between gap-4">
              <span className="text-body-sm text-fg-muted">{FOLDER_LABEL[folder]}</span>
              <Select
                className="w-40"
                ariaLabel={`Retention for ${folder}`}
                value={String(retention[folder])}
                options={
                  RETENTION_OPTIONS.some((o) => o.value === String(retention[folder]))
                    ? RETENTION_OPTIONS
                    : [...RETENTION_OPTIONS, { value: String(retention[folder]), label: `${retention[folder]} days` }]
                }
                onChange={(next) =>
                  void api.setRetention({ [folder]: Number(next) }).then(setRetention)
                }
              />
            </div>
          ))}
      </section>

      <section className="mb-8">
        <h3 className="mb-2 text-body font-semibold">Encrypted backup</h3>
        <p className="mb-3 text-body-sm text-fg-muted">
          Conversations, memories, workflows and reminders, encrypted with your passphrase. API keys are
          never included.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="Passphrase (8+ characters)"
            aria-label="Backup passphrase"
            className="w-64 rounded bg-white/5 px-3 py-1.5 text-body-sm text-fg outline-none placeholder:text-fg-faint focus:bg-white/10"
          />
          <button
            onClick={() => void exportBackup()}
            disabled={busy || !passphraseOk || !backendOnline}
            className={`${BUTTON} bg-accent/20 text-accent-bright enabled:hover:bg-accent/30`}
          >
            Export
          </button>
          <button
            onClick={() => importInput.current?.click()}
            disabled={busy || !passphraseOk || !backendOnline}
            className={`${BUTTON} bg-white/10 text-fg enabled:hover:bg-white/15`}
          >
            Import…
          </button>
          <input
            ref={importInput}
            type="file"
            accept=".corvusbak"
            hidden
            onChange={(e) => void importBackup(e.target.files?.[0])}
          />
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-body font-semibold text-danger">Delete all my data</h3>
        <p className="mb-3 text-body-sm text-fg-muted">
          Removes everything Corvus stored on this computer. Downloaded models stay so you don&rsquo;t have
          to fetch them again.
        </p>
        <button
          onClick={() => void wipe()}
          disabled={busy || !backendOnline}
          className={`${BUTTON} bg-danger/15 text-danger enabled:hover:bg-danger/25`}
        >
          Delete all my data…
        </button>
      </section>

      {status && (
        <p role="status" className={`mt-6 text-body-sm ${status.ok ? "text-success" : "text-danger"}`}>
          {status.text}
        </p>
      )}
    </>
  );
}
