import { useCallback, useEffect, useState } from "react";
import { api, type Reminder } from "../lib/api";
import { useCorvus } from "../state/store";

const KIND_LABEL: Record<string, string> = {
  timer: "Timer",
  alarm: "Alarm",
  reminder: "Reminder",
};

function dueText(fireAt: string): string {
  const due = new Date(fireAt);
  const deltaMin = Math.round((due.getTime() - Date.now()) / 60000);
  const abs = due.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  if (deltaMin <= 0) return `due now — ${abs}`;
  if (deltaMin < 60) return `in ${deltaMin} min — ${abs}`;
  if (deltaMin < 60 * 24) return `in ${Math.round(deltaMin / 60)} h — ${abs}`;
  return abs;
}

/** Pending reminders/timers/alarms set via chat, with cancel. Fills the gap
 * where reminders could be created but never reviewed or cancelled. */
export function RemindersPanel() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => {
    try {
      setReminders(await api.listReminders());
    } catch {
      setReminders([]);
    }
  }, []);

  useEffect(() => {
    if (!backendOnline) return;
    void refresh();
    // Fired reminders leave the pending list on the backend; a light poll
    // keeps the panel honest without wiring another socket.
    const timer = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(timer);
  }, [backendOnline, refresh]);

  async function cancel(id: number) {
    try {
      await api.cancelReminder(id);
    } finally {
      void refresh();
    }
  }

  return (
    <section className="mb-6">
      <h2 className="mb-1 text-h4">Reminders</h2>
      <p className="mb-3 text-body-sm text-fg-muted">
        Timers, alarms, and reminders you&rsquo;ve set. Cancel one and it never fires.
      </p>
      {reminders.length === 0 ? (
        <p className="text-body text-fg-muted">
          No pending reminders — ask Corvus in chat to set one.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {reminders.map((r) => (
            <li key={r.id} className="glass flex items-center gap-3 rounded p-2.5 text-body-sm">
              <span className="rounded-sm bg-accent/15 px-1.5 py-0.5 text-caption text-accent-bright">
                {KIND_LABEL[r.kind] ?? "Reminder"}
              </span>
              <span className="flex-1 truncate text-fg">{r.text}</span>
              <span className="text-caption text-fg-faint">{dueText(r.fire_at)}</span>
              <button
                onClick={() => void cancel(r.id)}
                className="rounded bg-white/5 px-2 py-1 text-caption text-fg-muted transition-colors duration-fast hover:bg-danger/20 hover:text-danger"
              >
                Cancel
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
