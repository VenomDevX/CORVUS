import { AnimatePresence, motion } from "framer-motion";
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
          className="titlebar-no-drag rounded px-3 py-1 text-body-sm text-fg-muted transition-colors duration-fast hover:bg-accent/10 hover:text-fg"
        >
          ✕ Exit voice mode
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

      <div className="flex items-center gap-4 pb-4">
        <label className="flex cursor-pointer items-center gap-2 text-body-sm text-fg-muted">
          <input
            type="checkbox"
            checked={voice.wakeEnabled}
            onChange={(e) => setWakeEnabled(e.target.checked)}
            className="accent-accent"
          />
          Always listening (&ldquo;Hey Corvus&rdquo;)
        </label>
        <button
          onClick={pushToTalk}
          disabled={orbState === "listening"}
          aria-label="Push to talk"
          className="rounded-full bg-accent p-5 text-h3 shadow-glow-strong transition-all duration-fast enabled:hover:bg-accent-bright disabled:opacity-60"
        >
          🎤
        </button>
        {orbState === "speaking" && (
          <button
            onClick={stopSpeaking}
            aria-label="Stop speaking"
            className="rounded bg-danger/20 px-4 py-2 text-body text-danger transition-colors duration-fast hover:bg-danger/30"
          >
            ⬛ Stop
          </button>
        )}
      </div>
    </motion.div>
  );
}
