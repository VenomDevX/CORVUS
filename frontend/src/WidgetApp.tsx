import { useEffect, useRef, useState } from "react";
import { ArrowUpIcon, Maximize2 } from "lucide-react";
import { api, streamChat } from "./lib/api";
import { MarkdownContent } from "./components/MarkdownContent";

/** Desktop widget: a compact always-on-top quick-ask pill. Streams one answer
 * at a time; the expand button hands off to the main window. */
export default function WidgetApp() {
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    const check = () =>
      void api
        .health()
        .then(() => !cancelled && setOnline(true))
        .catch(() => !cancelled && setOnline(false));
    check();
    const timer = setInterval(check, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  function ask() {
    const content = text.trim();
    if (!content || busy || !online) return;
    setText("");
    setAnswer("");
    setBusy(true);
    streamChat({ conversationId: null, content }, (frame) => {
      if (frame.type === "delta") setAnswer((a) => a + frame.content);
      if (frame.type === "error") setAnswer((a) => a + `\n> ⚠️ ${frame.message}`);
      if (frame.type === "done" || frame.type === "error") setBusy(false);
    }, () => setBusy(false));
  }

  return (
    <div className="flex h-screen flex-col gap-2 p-2">
      <div className="liquid-glass flex items-center gap-2 rounded-full px-3 py-2">
        <span
          className="titlebar-drag h-3 w-3 shrink-0 cursor-grab rounded-full"
          style={{ background: online ? "var(--c-accent)" : "#e5484d" }}
          title={online ? "Corvus online — drag to move" : "Corvus core offline"}
        />
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder={online ? "Ask Corvus…" : "Corvus core offline"}
          disabled={!online || busy}
          className="min-w-0 flex-1 bg-transparent text-body-sm text-fg placeholder:text-fg-faint focus:outline-none"
        />
        <button
          onClick={ask}
          disabled={!online || busy || !text.trim()}
          aria-label="Send"
          className="rounded-full bg-accent/20 p-1.5 text-accent-bright transition-colors duration-fast enabled:hover:bg-accent/30 disabled:opacity-40"
        >
          <ArrowUpIcon className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => void window.corvus?.showMain()}
          aria-label="Open Corvus"
          title="Open Corvus"
          className="rounded-full bg-white/5 p-1.5 text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      </div>
      {(answer || busy) && (
        <div className="liquid-glass min-h-0 flex-1 overflow-y-auto rounded-xl px-3 py-2 text-body-sm text-fg">
          {answer ? <MarkdownContent content={answer} /> : <span className="text-fg-muted">Thinking…</span>}
        </div>
      )}
    </div>
  );
}
