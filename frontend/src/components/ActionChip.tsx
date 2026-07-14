import type { ActionEvent } from "../state/store";

const STATUS_STYLE: Record<ActionEvent["status"], { icon: string; cls: string }> = {
  proposed: { icon: "•", cls: "text-fg-muted" },
  confirming: { icon: "⏳", cls: "text-warning" },
  ok: { icon: "✓", cls: "text-success" },
  failed: { icon: "✕", cls: "text-danger" },
  declined: { icon: "⊘", cls: "text-fg-faint" },
};

const RISK_STYLE: Record<string, string> = {
  safe: "bg-white/5 text-fg-muted",
  low: "bg-accent/15 text-accent-bright",
  medium: "bg-warning/15 text-warning",
  high: "bg-danger/15 text-danger",
};

function summarizeArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k}: ${String(v)}`).join(", ");
}

/** Compact record of an action Corvus proposed/ran, shown under its message. */
export function ActionChip({ action }: { action: ActionEvent }) {
  const status = STATUS_STYLE[action.status];
  const args = summarizeArgs(action.arguments);
  return (
    <div className="glass flex items-center gap-2 rounded px-2.5 py-1.5 text-body-sm">
      <span className={status.cls}>{status.icon}</span>
      <span className="font-mono text-mono text-fg">{action.name}</span>
      <span className={`rounded-sm px-1.5 py-0.5 text-caption ${RISK_STYLE[action.risk] ?? ""}`}>
        {action.risk}
      </span>
      {args && <span className="truncate text-fg-faint">{args}</span>}
      {action.message && (action.status === "failed" || action.status === "declined") && (
        <span className="text-fg-muted">— {action.message}</span>
      )}
    </div>
  );
}
