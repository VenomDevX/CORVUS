import { motion } from "framer-motion";
import type { RiskTier } from "../lib/api";
import { useCorvus } from "../state/store";

// Only medium/high actions ever reach a confirmation, and the two must look
// different: a folder rename shouldn't wear the same red as a disk wipe.
const RISK_BADGE: Record<RiskTier, string> = {
  safe: "bg-white/5 text-fg-muted",
  low: "bg-accent/15 text-accent-bright",
  medium: "bg-warning/15 text-warning",
  high: "bg-danger/15 text-danger",
};
const RISK_BORDER: Record<RiskTier, string> = {
  safe: "border-white/10",
  low: "border-accent/40",
  medium: "border-warning/40",
  high: "border-danger/50",
};

/** Explicit consequence prompt for a risky action. States exactly what will
 * happen (from the backend), never a generic "Are you sure?". */
export function ConfirmationCard() {
  const pending = useCorvus((s) => s.pendingConfirmation);
  const answer = useCorvus((s) => s.answerConfirmation);
  if (!pending) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass rounded-lg border p-4 shadow-glass-2 ${RISK_BORDER[pending.risk]}`}
      role="alertdialog"
      aria-label="Action confirmation"
    >
      <div className="mb-1 flex items-center gap-2">
        <span className={pending.risk === "high" ? "text-danger" : "text-warning"}>⚠️</span>
        <span className="text-h4 text-fg">Confirm action</span>
        <span className={`rounded-sm px-1.5 py-0.5 text-caption ${RISK_BADGE[pending.risk]}`}>
          {pending.risk} risk
        </span>
      </div>
      <p className="mb-3 text-body text-fg">{pending.prompt}</p>
      <div className="flex gap-2">
        <button
          onClick={() => answer(true)}
          className={`rounded px-4 py-2 text-body font-medium text-white transition-colors duration-fast ${
            pending.risk === "high"
              ? "bg-danger hover:bg-danger/85"
              : "bg-accent shadow-glow hover:bg-accent-bright"
          }`}
        >
          Yes, do it
        </button>
        <button
          onClick={() => answer(false)}
          className="rounded bg-white/10 px-4 py-2 text-body text-fg transition-colors duration-fast hover:bg-white/15"
        >
          Cancel
        </button>
      </div>
    </motion.div>
  );
}
