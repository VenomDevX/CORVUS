import { useEffect, useRef, useState } from "react";
import { Copy, Check, Edit2 } from "lucide-react";
import { motion } from "framer-motion";
import { Orb } from "./Orb";
import { MarkdownContent } from "./MarkdownContent";
import { InputBar } from "./InputBar";

import { ConfirmationCard } from "./ConfirmationCard";
import { ThinkingAnimation } from "./ThinkingAnimation";
import { useCorvus } from "../state/store";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";

function MessageActionButtons({ content, onEdit, className = "" }: { content: string; onEdit?: () => void; className?: string }) {
  const [copied, setCopied] = useState(false);
  
  function copy() {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className={`flex items-center gap-1 ${className}`}>
      {onEdit && (
        <button
          onClick={onEdit}
          title="Edit message"
          aria-label="Edit message"
          className="rounded p-1 transition-colors duration-fast text-fg-muted hover:text-fg hover:bg-white/5"
        >
          <Edit2 className="h-4 w-4" />
        </button>
      )}
      <button
        onClick={copy}
        title="Copy message"
        aria-label="Copy message"
        className="rounded p-1 transition-colors duration-fast text-fg-muted hover:text-fg hover:bg-white/5"
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </button>
    </div>
  );
}

function MessageItem({ m, index, initialCount }: { m: any, index: number, initialCount: React.MutableRefObject<number> }) {
  const actions = "actions" in m ? m.actions : undefined;
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(m.content ?? "");
  const send = useCorvus((s) => s.send);

  return (
    <motion.div
      key={"id" in m ? m.id : index}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.18,
        ease: "easeOut",
        delay: index < initialCount.current ? Math.min(index * 0.03, 0.3) : 0,
      }}
      className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
    >
      {m.role === "user" ? (
        <div className={`flex flex-col items-end gap-1 group max-w-[80%] ${isEditing ? "w-full" : ""}`}>
          {isEditing ? (
            <div className="liquid-glass rounded-xl px-4 py-3 text-fg w-full flex flex-col gap-2">
              <Textarea 
                value={editContent} 
                onChange={(e) => setEditContent(e.target.value)} 
                className="min-h-[100px] text-fg bg-transparent border-white/20 focus-visible:ring-0" 
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => { setIsEditing(false); setEditContent(m.content ?? ""); }} className="text-fg border-white/20 hover:bg-white/5">Cancel</Button>
                <Button size="sm" onClick={() => { send(editContent, m.id); setIsEditing(false); }}>Save & Submit</Button>
              </div>
            </div>
          ) : (
            <div className="liquid-glass rounded-xl px-4 py-3 text-fg">
              {m.content && <MarkdownContent content={m.content} />}
            </div>
          )}
          {!isEditing && (
            <MessageActionButtons content={m.content ?? ""} onEdit={() => setIsEditing(true)} className="text-fg-muted opacity-0 group-hover:opacity-100 transition-opacity" />
          )}
        </div>
      ) : (
        <>
          {m.content ? (
            <div className="flex flex-col items-start gap-1 max-w-[80%] group">
              <div className="px-4 py-3 text-fg">
                <MarkdownContent content={m.content} />
              </div>
              <div className="flex w-full justify-start items-start gap-1 pl-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <MessageActionButtons content={m.content ?? ""} className="text-fg-muted" />
              </div>
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
      {/* Action chips hidden — tool execution is internal, not user-facing */}
    </motion.div>
  );
}

export function ChatView() {
  const messages = useCorvus((s) => s.messages);
  const orbState = useCorvus((s) => s.orbState);
  const level = useCorvus((s) => s.voice.level);
  const generating = useCorvus((s) => s.generating);
  const scroller = useRef<HTMLDivElement>(null);
  // Stagger only the bubbles present on first render (history load); messages
  // that arrive live should appear immediately.
  const initialCount = useRef(messages.length);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  const empty = messages.length === 0;

  return (
    <div className="relative flex h-full flex-col gap-3">
      <div className={`pointer-events-none ${empty ? "flex flex-1 flex-col items-center justify-center gap-6" : "absolute inset-0 z-0 overflow-hidden"}`}>
        <Orb state={orbState} level={level} backgroundMode={!empty} />
        {empty && (
          <div className="text-center">
            <h1 className="text-h1 tracking-tight">Corvus</h1>
            <p className="mt-1 text-body text-fg-muted">
              Ask anything, or just say &ldquo;Hey Corvus&rdquo;.
            </p>
          </div>
        )}
      </div>

      {!empty && (
        <div ref={scroller} className="relative z-10 flex min-h-0 flex-1 flex-col items-center overflow-y-auto overflow-x-hidden pt-2 pb-4">
          <div className="w-full max-w-4xl space-y-8 px-4 md:px-8">
            {messages.map((m, i) => (
              <MessageItem key={"id" in m ? m.id : i} m={m} index={i} initialCount={initialCount} />
            ))}
            {generating && <div className="h-2" aria-live="polite" />}
          </div>
        </div>
      )}
      <div className="relative z-10 flex w-full justify-center pb-2">
        <div className="w-full max-w-4xl px-4 md:px-8">
          <ConfirmationCard />
          <InputBar />
        </div>
      </div>
    </div>
  );
}
