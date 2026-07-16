import { useEffect, useRef } from "react";
import { Orb } from "./Orb";
import { MarkdownContent } from "./MarkdownContent";
import { InputBar } from "./InputBar";
import { ActionChip } from "./ActionChip";
import { ConfirmationCard } from "./ConfirmationCard";
import { ThinkingAnimation } from "./ThinkingAnimation";
import { useCorvus } from "../state/store";

export function ChatView() {
  const messages = useCorvus((s) => s.messages);
  const orbState = useCorvus((s) => s.orbState);
  const level = useCorvus((s) => s.voice.level);
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
          <Orb state={orbState} level={level} />
          <div className="text-center">
            <h1 className="text-h1 tracking-tight">Corvus</h1>
            <p className="mt-1 text-body text-fg-muted">
              Ask anything, or just say &ldquo;Hey Corvus&rdquo;.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-4">
          <div ref={scroller} className="min-w-0 flex-1 space-y-4 overflow-y-auto px-8 pt-2 pb-4">
            {messages.map((m, i) => {
              const actions = "actions" in m ? m.actions : undefined;
              return (
                <div key={"id" in m ? m.id : i} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
                  {m.role === "user" ? (
                    <div className="liquid-glass-accent max-w-[80%] rounded-xl px-4 py-3 text-fg">
                      {m.content && <MarkdownContent content={m.content} />}
                    </div>
                  ) : (
                    <>
                      {m.content ? (
                        <div className="liquid-glass max-w-[80%] rounded-xl px-4 py-3 text-fg">
                          <MarkdownContent content={m.content} />
                        </div>
                      ) : actions && actions.length > 0 ? (
                        <div className="liquid-glass max-w-[80%] rounded-xl px-4 py-3 text-fg">
                          <span className="text-fg-muted">Corvus is working…</span>
                        </div>
                      ) : (
                        <div className="max-w-[80%] py-2 text-fg">
                          <ThinkingAnimation />
                        </div>
                      )}
                    </>
                  )}
                  {actions && actions.length > 0 && (
                    <div className="mt-2 flex max-w-[80%] flex-col gap-1.5">
                      {actions.map((a, j) => (
                        <ActionChip key={`${a.name}-${j}`} action={a} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {generating && <div className="h-2" aria-live="polite" />}
          </div>

        </div>
      )}
      <ConfirmationCard />
      <InputBar />
    </div>
  );
}
