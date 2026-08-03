import type { ReactNode } from "react";

export function SectionShell({ title, actions, children, fullWidth }: { title: string; actions?: ReactNode; children: ReactNode; fullWidth?: boolean }) {
  if (fullWidth) {
    return (
      <div className="flex h-full flex-col gap-4 overflow-hidden">
        <div className="flex items-center justify-between">
          <h1 className="text-h2 tracking-tight">{title}</h1>
          {actions}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">{children}</div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full justify-center">
      <div className="flex h-full w-full max-w-5xl flex-col gap-4 overflow-hidden px-4 md:px-8">
        <div className="flex items-center justify-between">
          <h1 className="text-h2 tracking-tight">{title}</h1>
          {actions}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">{children}</div>
      </div>
    </div>
  );
}

/** View for sections whose backing system ships in a later milestone. */
export function UpcomingSection({ title, milestone, detail }: { title: string; milestone: number; detail: string }) {
  return (
    <SectionShell title={title}>
      <div className="glass flex h-64 flex-col items-center justify-center gap-2 rounded-lg text-center">
        <span className="text-h3 text-fg">{title} arrives in Milestone {milestone}</span>
        <p className="max-w-md text-body text-fg-muted">{detail}</p>
      </div>
    </SectionShell>
  );
}
