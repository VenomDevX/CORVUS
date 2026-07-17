import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { api, type Memory } from "../lib/api";
import { useCorvus } from "../state/store";
import { MemoryGraph } from "../components/MemoryGraph";

const CATEGORY_LABEL: Record<Memory["category"], string> = {
  preference: "Preference",
  project: "Project",
  person: "Person",
  app: "App",
};

export function MemoryView() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [view, setView] = useState<"list" | "graph">("list");
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setMemories(await api.listMemories()), []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  async function remove(id: number) {
    await api.deleteMemory(id);
    await refresh();
  }

  return (
    <SectionShell
      title="Memory"
      actions={
        <span className="flex items-center gap-2">
          <span className="flex overflow-hidden rounded border border-white/10">
            {(["list", "graph"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 text-body-sm capitalize transition-colors duration-fast ${
                  view === v ? "bg-accent/20 text-accent-bright" : "text-fg-muted hover:bg-white/5"
                }`}
              >
                {v}
              </button>
            ))}
          </span>
        <a
          href={api.exportMemoriesUrl()}
          download="corvus-memories.json"
          className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
        >
          Export JSON
        </a>
        </span>
      }
    >
      <p className="mb-3 text-body-sm text-fg-muted">
        Everything Corvus remembers is listed here — nothing is stored silently. Delete anything you
        don&rsquo;t want kept.
      </p>
      {view === "graph" && memories.length > 0 ? (
        <MemoryGraph memories={memories} onDelete={(id) => void remove(id)} />
      ) : memories.length === 0 ? (
        <p className="text-body text-fg-muted">
          Corvus hasn&rsquo;t stored any memories yet. Durable facts from your chats (preferences,
          projects, people, favorite apps) will appear here.
        </p>
      ) : (
        <ul className="space-y-2">
          {memories.map((m) => (
            <li key={m.id} className="glass flex items-start justify-between rounded p-3">
              <div className="min-w-0 flex-1">
                <span className="mr-2 rounded-sm bg-accent/20 px-1.5 py-0.5 text-caption text-accent-bright">
                  {CATEGORY_LABEL[m.category]}
                </span>
                <span className="text-body text-fg">{m.content}</span>
                <div className="mt-1 text-caption text-fg-faint">
                  {new Date(m.created_at + "Z").toLocaleString()}
                </div>
              </div>
              <button
                onClick={() => void remove(m.id)}
                aria-label="Delete this memory"
                className="ml-3 rounded px-2 py-1 text-caption text-fg-faint transition-colors duration-fast hover:bg-danger/20 hover:text-danger"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}
