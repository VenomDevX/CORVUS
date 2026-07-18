import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import { useCorvus } from "./state/store";
import { api } from "./lib/api";

export default function OverlayApp() {
  const orbState = useCorvus((s) => s.orbState);
  const connectVoiceSocket = useCorvus((s) => s.connectVoiceSocket);
  const backendOnline = useCorvus((s) => s.backendOnline);
  const setBackendOnline = useCorvus((s) => s.setBackendOnline);

  // Background polling to know when backend is up so we can connect WebSocket
  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        await api.health();
        if (!cancelled) setBackendOnline(true);
      } catch {
        if (!cancelled) setBackendOnline(false);
      }
    }
    void check();
    const timer = setInterval(check, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [setBackendOnline]);

  useEffect(() => {
    if (backendOnline) connectVoiceSocket();
  }, [backendOnline, connectVoiceSocket]);

  return (
    <div className="w-full h-full overflow-visible">
      <AnimatePresence>
        {orbState === "listening" && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ 
              opacity: [0.7, 1, 0.7], 
              y: 0,
              boxShadow: [
                "0 0 10px 2px rgba(255,255,255,0.6), 0 0 20px 4px rgba(255,255,255,0.4)",
                "0 0 15px 5px rgba(255,255,255,1), 0 0 30px 8px rgba(255,255,255,0.8)",
                "0 0 10px 2px rgba(255,255,255,0.6), 0 0 20px 4px rgba(255,255,255,0.4)"
              ]
            }}
            exit={{ opacity: 0, y: -10, boxShadow: "none", transition: { duration: 0.2 } }}
            transition={{ 
              y: { duration: 0.2 },
              opacity: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
              boxShadow: { duration: 1.5, repeat: Infinity, ease: "easeInOut" }
            }}
            className="w-full h-[1px] bg-transparent"
          />
        )}
      </AnimatePresence>
    </div>
  );
}
