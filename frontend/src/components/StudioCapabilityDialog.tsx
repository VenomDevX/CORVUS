import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Blocks, CheckCircle2, CircleDashed, X } from "lucide-react";
import { api, type Plugin } from "../lib/api";
import { useCorvus } from "../state/store";
import { AddPluginButton } from "./AddPluginButton";

/** Popup behind the Studio's Image / Video / Sound Effects tabs: these
 * capabilities arrive as plugins, so the dialog shows the live plugin catalog
 * (what's installed and actually working) plus install/browse entry points. */
export function StudioCapabilityDialog({
  capability,
  onClose,
}: {
  capability: string | null;
  onClose: () => void;
}) {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const setSection = useCorvus((s) => s.setSection);
  const [plugins, setPlugins] = useState<Plugin[]>([]);

  useEffect(() => {
    if (capability && backendOnline) {
      void api.listPlugins().then(setPlugins).catch(() => setPlugins([]));
    }
  }, [capability, backendOnline]);

  return (
    <AnimatePresence>
      {capability && (
        <motion.div
          className="fixed inset-0 z-[95] flex items-center justify-center bg-black/50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            className="liquid-glass w-full max-w-md rounded-2xl p-6"
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            role="dialog"
            aria-label={`${capability} extensions`}
          >
            <div className="mb-1 flex items-start justify-between">
              <h2 className="text-h3 tracking-tight text-fg">{capability} — via extensions</h2>
              <button
                onClick={onClose}
                aria-label="Close"
                className="rounded p-1 text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="mb-4 text-body-sm text-fg-muted">
              {capability} generation isn&rsquo;t built into the core app — it plugs in as an
              extension. Install one below, or browse everything in the Extensions section.
            </p>

            <div className="mb-4 max-h-56 space-y-1.5 overflow-y-auto">
              {plugins.length === 0 ? (
                <p className="rounded bg-white/5 p-3 text-body-sm text-fg-muted">
                  {backendOnline
                    ? "No plugins installed yet."
                    : "Corvus core is offline — plugin list unavailable."}
                </p>
              ) : (
                plugins.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 rounded bg-white/5 p-2.5">
                    <Blocks className="h-4 w-4 shrink-0 text-accent-bright" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-body-sm font-semibold text-fg">{p.name}</div>
                      <div className="truncate text-caption text-fg-faint">{p.description}</div>
                    </div>
                    {p.loaded ? (
                      <span className="flex shrink-0 items-center gap-1 text-caption text-success">
                        <CheckCircle2 className="h-3.5 w-3.5" /> working
                      </span>
                    ) : (
                      <span className="flex shrink-0 items-center gap-1 text-caption text-fg-faint">
                        <CircleDashed className="h-3.5 w-3.5" /> {p.enabled ? "needs permissions" : "off"}
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="flex items-center justify-between gap-2">
              <button
                onClick={() => {
                  onClose();
                  setSection("extensions");
                }}
                className="rounded bg-accent/20 px-4 py-2 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
              >
                Browse Extensions
              </button>
              <AddPluginButton
                onInstalled={() => void api.listPlugins().then(setPlugins).catch(() => undefined)}
              />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
