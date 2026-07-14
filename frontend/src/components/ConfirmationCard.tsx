import { motion } from "framer-motion";
import { useCorvus } from "../state/store";

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
      className="glass rounded-lg border border-warning/40 p-4 shadow-glass-2"
      role="alertdialog"
      aria-label="Action confirmation"
    >
      <div className="mb-1 flex items-center gap-2">
        <span className="text-warning">⚠️</span>
        <span className="text-h4 text-fg">Confirm action</span>
        <span className="rounded-sm bg-danger/15 px-1.5 py-0.5 text-caption text-danger">
          {pending.risk} risk
        </span>
      </div>
      <p className="mb-3 text-body text-fg">{pending.prompt}</p>
      <div className="flex gap-2">
        <button
          onClick={() => answer(true)}
          className="rounded bg-accent px-4 py-2 text-body font-medium text-white shadow-glow transition-colors duration-fast hover:bg-accent-bright"
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
