import { AnimatePresence, motion } from "framer-motion";
import { Mic, Square, X } from "lucide-react";
import { Orb } from "./Orb";
import { useCorvus } from "../state/store";

const STATUS_TEXT: Record<string, string> = {
  idle: "Say “Hey Corvus” or tap the mic",
  listening: "Corvus is listening…",
  thinking: "Corvus is thinking…",
  speaking: "Corvus is speaking",
};

/** Voice-first layout: the whole UI collapses to the orb, live captions,
 * and voice controls. Entered via the voice toggle, the mic button, or a
 * wake-word detection. */
export function VoiceMode() {
  const orbState = useCorvus((s) => s.orbState);
  const voice = useCorvus((s) => s.voice);
  const setVoiceMode = useCorvus((s) => s.setVoiceMode);
  const pushToTalk = useCorvus((s) => s.pushToTalk);
  const setWakeEnabled = useCorvus((s) => s.setWakeEnabled);
  const stopSpeaking = useCorvus((s) => s.stopSpeaking);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="app-bg absolute inset-0 z-50 flex flex-col items-center justify-between p-8"
    >
      <div className="titlebar-drag flex h-10 w-full items-center justify-end">
        <button
          onClick={() => setVoiceMode(false)}
          aria-label="Exit voice mode"
          className="titlebar-no-drag flex items-center gap-2 rounded-full glass px-4 py-1.5 text-body-sm text-fg-muted transition-colors duration-fast hover:text-fg hover:bg-white/10"
        >
          <X size={16} /> Exit
        </button>
      </div>

      <div className="flex flex-col items-center gap-6">
        <Orb state={orbState} level={voice.level} size={280} />
        <div className="text-center">
          <p className="text-h3 text-fg">{STATUS_TEXT[orbState] ?? orbState}</p>
          {!voice.available && voice.error && (
            <p className="mt-2 max-w-md text-body-sm text-danger">
              Voice unavailable: {voice.error}
            </p>
          )}
        </div>

        <div className="min-h-24 max-w-2xl space-y-3 text-center">
          <AnimatePresence>
            {voice.transcript && (
              <motion.p
                key="transcript"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-body text-fg-muted"
              >
                &ldquo;{voice.transcript}&rdquo;
              </motion.p>
            )}
          </AnimatePresence>
          {voice.assistantLive && (
            <p className="max-h-40 overflow-y-auto text-body text-fg">{voice.assistantLive}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-6 pb-6">
        <label className="flex cursor-pointer items-center gap-2 text-body-sm text-fg-muted transition-colors hover:text-fg">
          <input
            type="checkbox"
            checked={voice.wakeEnabled}
            onChange={(e) => setWakeEnabled(e.target.checked)}
            className="accent-accent h-4 w-4 rounded border-white/20 bg-black/20"
          />
          Always listening (&ldquo;Hey Corvus&rdquo;)
        </label>
        
        <button
          onClick={pushToTalk}
          disabled={orbState === "listening"}
          aria-label="Push to talk"
          className="group relative flex h-16 w-16 items-center justify-center rounded-full bg-accent text-white shadow-glow-strong transition-all duration-300 enabled:hover:scale-105 enabled:hover:bg-accent-bright disabled:opacity-50 disabled:scale-95"
        >
          <div className="absolute inset-0 rounded-full bg-white/20 opacity-0 transition-opacity group-hover:opacity-100" />
          <Mic size={28} className={orbState === "listening" ? "animate-pulse" : ""} />
        </button>
        
        <div className="w-[140px]"> {/* Fixed width container to keep mic centered */}
          <AnimatePresence>
            {orbState === "speaking" && (
              <motion.button
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                onClick={stopSpeaking}
                aria-label="Stop speaking"
                className="flex items-center gap-2 rounded-full glass border-danger/30 bg-danger/10 px-4 py-2 text-body text-danger transition-all duration-fast hover:bg-danger/20 hover:border-danger/50"
              >
                <Square size={16} className="fill-current" /> Stop
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
