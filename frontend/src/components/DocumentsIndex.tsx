import { useCallback, useEffect, useState } from "react";
import { api, type RagHit, type RagStatus } from "../lib/api";
import { useCorvus } from "../state/store";

/** Settings section for the local documents index: point Corvus at a folder,
 * index it, and it can answer from your files — entirely offline. */
export function DocumentsIndex() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [folder, setFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<RagHit[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.ragStatus();
      setStatus(s);
      setFolder((f) => f || s.folder);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  // Poll progress while an index run is going.
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void refresh(), 1000);
    return () => clearInterval(timer);
  }, [busy, refresh]);

  async function runIndex() {
    if (!folder.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      const r = await api.ragIndex(folder.trim());
      setMessage(`Indexed ${r.files} files (${r.added} new/changed, ${r.skipped} unchanged).`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "indexing failed");
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  async function trySearch() {
    if (!query.trim()) return;
    try {
      setHits(await api.ragSearch(query.trim()));
    } catch {
      setHits([]);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-body-sm text-fg-muted">
        Index a folder of documents (.md, .txt, .pdf, code files) and Corvus can answer questions
        from them in chat — everything stays on this PC.
      </p>
      <div className="flex gap-2">
        <input
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
          placeholder="C:\Users\you\Documents\notes"
          className="glass min-w-0 flex-1 rounded px-3 py-2 text-body-sm text-fg placeholder:text-fg-faint focus:outline-none"
        />
        <button
          onClick={() => void runIndex()}
          disabled={busy || !backendOnline || !folder.trim()}
          className="rounded bg-accent px-4 py-2 text-body-sm text-white transition-colors duration-fast enabled:hover:bg-accent-bright disabled:opacity-40"
        >
          {busy
            ? status?.progress.total
              ? `Indexing ${status.progress.done}/${status.progress.total}…`
              : "Indexing…"
            : status?.files
              ? "Re-index"
              : "Index folder"}
        </button>
      </div>
      {status && (
        <p className="text-caption text-fg-faint">
          {status.files} files · {status.chunks} passages indexed · semantic search{" "}
          {status.embeddings ? "on" : "off"}
          {!status.embeddings && (
            <> — run <code className="rounded-sm bg-white/10 px-1 font-mono">ollama pull nomic-embed-text</code> to enable it</>
          )}
        </p>
      )}
      {message && <p className="text-body-sm text-fg-muted">{message}</p>}

      {(status?.chunks ?? 0) > 0 && (
        <div className="space-y-2 border-t border-white/10 pt-3">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void trySearch()}
              placeholder="Try a search…"
              className="glass min-w-0 flex-1 rounded px-3 py-2 text-body-sm text-fg placeholder:text-fg-faint focus:outline-none"
            />
            <button
              onClick={() => void trySearch()}
              className="rounded bg-accent/20 px-3 py-2 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
            >
              Search
            </button>
          </div>
          {hits !== null &&
            (hits.length === 0 ? (
              <p className="text-body-sm text-fg-muted">No matches.</p>
            ) : (
              <ul className="space-y-1.5">
                {hits.map((h, i) => (
                  <li key={i} className="glass rounded p-2.5 text-body-sm">
                    <div className="mb-1 font-mono text-caption text-accent-bright">
                      {h.path.split(/[\\/]/).pop()}
                    </div>
                    <div className="line-clamp-3 text-fg-muted">{h.content}</div>
                  </li>
                ))}
              </ul>
            ))}
        </div>
      )}
    </div>
  );
}
