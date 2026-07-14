import { useEffect, useRef } from "react";
import { Orb } from "./Orb";
import { MarkdownContent } from "./MarkdownContent";
import { InputBar } from "./InputBar";
import { useCorvus } from "../state/store";

export function ChatView() {
  const messages = useCorvus((s) => s.messages);
  const orbState = useCorvus((s) => s.orbState);
  const generating = useCorvus((s) => s.generating);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col gap-3">
      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6">
          <Orb state={orbState} />
          <div className="text-center">
            <h1 className="text-h1 tracking-tight">Corvus</h1>
            <p className="mt-1 text-body text-fg-muted">
              Ask anything, or say &ldquo;Hey Corvus&rdquo; once voice lands.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-4">
          <div ref={scroller} className="min-w-0 flex-1 space-y-4 overflow-y-auto pr-2 pt-2">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-3 ${
                    m.role === "user"
                      ? "bg-accent/20 text-fg"
                      : "glass text-fg shadow-glass-1"
                  }`}
                >
                  {m.content ? (
                    <MarkdownContent content={m.content} />
                  ) : (
                    <span className="text-fg-muted">Corvus is thinking…</span>
                  )}
                </div>
              </div>
            ))}
            {generating && <div className="h-2" aria-live="polite" />}
          </div>
          <div className="hidden w-56 shrink-0 items-start justify-center pt-4 xl:flex">
            <Orb state={orbState} size={140} />
          </div>
        </div>
      )}
      <InputBar />
    </div>
  );
}
