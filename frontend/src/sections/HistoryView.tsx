import { useEffect } from "react";
import { SectionShell } from "./SectionShell";
import { useCorvus } from "../state/store";
import { api } from "../lib/api";

export function HistoryView() {
  const conversations = useCorvus((s) => s.conversations);
  const refresh = useCorvus((s) => s.refreshConversations);
  const open = useCorvus((s) => s.openConversation);
  const backendOnline = useCorvus((s) => s.backendOnline);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  async function remove(id: number) {
    await api.deleteConversation(id);
    await refresh();
  }

  return (
    <SectionShell title="History">
      {conversations.length === 0 ? (
        <p className="text-body text-fg-muted">No conversations yet — start one from the Chat section.</p>
      ) : (
        <ul className="space-y-2">
          {conversations.map((c) => (
            <li key={c.id} className="glass flex items-center justify-between rounded p-3">
              <button onClick={() => void open(c.id)} className="min-w-0 flex-1 text-left">
                <div className="truncate text-body text-fg">{c.title}</div>
                <div className="text-caption text-fg-faint">
                  {new Date(c.updated_at + "Z").toLocaleString()}
                </div>
              </button>
              <button
                onClick={() => void remove(c.id)}
                aria-label={`Delete conversation "${c.title}"`}
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
