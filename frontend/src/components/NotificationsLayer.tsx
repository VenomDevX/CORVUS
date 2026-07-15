import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { connectNotifications, type NotificationEvent } from "../lib/api";
import { useCorvus } from "../state/store";

interface Toast {
  id: number;
  title: string;
  message: string;
  kind: "notify" | "reminder";
}

/** Bridges backend notifications/reminders to native Windows toasts (via the
 * renderer's Notification API) and an in-app toast stack. Stays connected while
 * the backend is online so reminders fire even when the window is in the tray. */
export function NotificationsLayer() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  useEffect(() => {
    if (!backendOnline) return;

    const raise = (event: NotificationEvent) => {
      const id = ++counter.current;
      const title = event.title;
      const message = event.message;
      setToasts((prev) => [...prev, { id, title, message, kind: event.type }]);
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
      // Native Windows toast (works from the hidden tray window too).
      try {
        if ("Notification" in window) new Notification(title, { body: message });
      } catch {
        /* renderer without notification support — the in-app toast still shows */
      }
    };

    // The backend health poll flips backendOnline, which re-runs this effect
    // and reconnects if the socket drops.
    const socket = connectNotifications(raise, () => {});
    return () => socket.close();
  }, [backendOnline]);

  return (
    <div className="pointer-events-none fixed right-4 top-12 z-[60] flex w-80 flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            className="glass pointer-events-auto rounded-lg border border-accent/30 p-3 shadow-glass-2"
          >
            <div className="flex items-center gap-2">
              <span aria-hidden>{t.kind === "reminder" ? "⏰" : "🔔"}</span>
              <span className="text-body font-semibold text-fg">{t.title}</span>
            </div>
            <p className="mt-1 text-body-sm text-fg-muted">{t.message}</p>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
