import { useCallback, useEffect, useState } from "react";
import { SectionShell } from "./SectionShell";
import { api, type ActionLogEntry, type ActionSpec, type RiskTier } from "../lib/api";
import { useCorvus } from "../state/store";
import { WorkflowsPanel } from "../components/WorkflowsPanel";
import { RemindersPanel } from "../components/RemindersPanel";
import { Tabs } from "../components/ui/Tabs";
import { DownloadsView } from "./DownloadsView";

const RISK_ORDER: RiskTier[] = ["safe", "low", "medium", "high"];
const RISK_STYLE: Record<RiskTier, string> = {
  safe: "bg-white/5 text-fg-muted",
  low: "bg-accent/15 text-accent-bright",
  medium: "bg-warning/15 text-warning",
  high: "bg-danger/15 text-danger",
};
const OUTCOME_STYLE: Record<ActionLogEntry["outcome"], string> = {
  executed: "text-success",
  declined: "text-fg-faint",
  failed: "text-danger",
};

type Tab = "workflows" | "reminders" | "activity" | "downloads" | "capabilities";

/** "search_documents" -> "Search documents": the log is for people, not code. */
const humanize = (name: string) => name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, " ");

/** Tasks section: workflows, reminders, what Corvus has done, browser
 * downloads, and the capabilities it can perform (the action registry). */
export function TasksView() {
  const [specs, setSpecs] = useState<ActionSpec[]>([]);
  const [log, setLog] = useState<ActionLogEntry[]>([]);
  const [tab, setTab] = useState<Tab>("workflows");
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => {
    const [s, l] = await Promise.all([api.listActionSpecs(), api.actionLog(100)]);
    setSpecs(s);
    setLog(l);
  }, []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  const byCategory = specs.reduce<Record<string, ActionSpec[]>>((acc, spec) => {
    (acc[spec.category] ??= []).push(spec);
    return acc;
  }, {});

  return (
    <SectionShell
      title="Tasks"
      actions={
        <button
          onClick={() => void refresh()}
          className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
        >
          Refresh
        </button>
      }
    >
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "workflows", label: "Workflows" },
          { value: "reminders", label: "Reminders" },
          { value: "activity", label: "Activity" },
          { value: "downloads", label: "Downloads" },
          { value: "capabilities", label: "What Corvus can do" },
        ]}
      />
      {tab === "workflows" && <WorkflowsPanel />}
      {tab === "reminders" && <RemindersPanel />}
      {tab === "downloads" && <DownloadsView />}

      {tab === "activity" && <section className="mb-6">
        <p className="mb-3 text-body-sm text-fg-muted">
          Everything Corvus has done on your PC, most recent first. High-risk actions were confirmed
          by you before running.
        </p>
        {log.length === 0 ? (
          <p className="text-body text-fg-muted">No actions run yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {log.map((entry) => (
              <li key={entry.id} className="glass flex items-center gap-2 rounded p-2.5 text-body-sm">
                <span className={OUTCOME_STYLE[entry.outcome]}>
                  {entry.outcome === "executed" ? "✓" : entry.outcome === "declined" ? "⊘" : "✕"}
                </span>
                <span className="shrink-0 text-fg" title={entry.action}>{humanize(entry.action)}</span>
                <span className="flex-1 truncate text-fg-muted">{entry.message}</span>
                <span className="text-caption text-fg-faint">
                  {new Date(entry.created_at + "Z").toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>}

      {tab === "capabilities" && <section>
        <p className="mb-3 text-body-sm text-fg-muted">
          {specs.length} actions across {Object.keys(byCategory).length} categories. Just ask in
          chat — Corvus picks the right one.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(byCategory).map(([category, items]) => (
            <div key={category} className="glass rounded-lg p-3">
              <h3 className="mb-2 text-body font-semibold capitalize text-fg">{category}</h3>
              <ul className="space-y-1.5">
                {[...items]
                  .sort((a, b) => RISK_ORDER.indexOf(a.risk) - RISK_ORDER.indexOf(b.risk))
                  .map((spec) => (
                    <li key={spec.name} className="flex items-start gap-2 text-body-sm">
                      <span className={`mt-0.5 rounded-sm px-1.5 py-0.5 text-caption ${RISK_STYLE[spec.risk]}`}>
                        {spec.risk}
                      </span>
                      <span className="text-fg-muted">{spec.description}</span>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      </section>}
    </SectionShell>
  );
}
