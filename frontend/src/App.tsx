import { useEffect, useRef } from "react";
import {
  FluentProvider,
  createDarkTheme,
  createLightTheme,
  type BrandVariants,
} from "@fluentui/react-components";
import { AnimatePresence } from "framer-motion";
import { Sidebar } from "./components/Sidebar";
import { ChatView } from "./components/ChatView";
import { VoiceMode } from "./components/VoiceMode";
import { NotificationsLayer } from "./components/NotificationsLayer";
import { HistoryView } from "./sections/HistoryView";
import { MemoryView } from "./sections/MemoryView";
import { SettingsView } from "./sections/SettingsView";
import { LogsView } from "./sections/LogsView";
import { TasksView } from "./sections/TasksView";
import { DownloadsView } from "./sections/DownloadsView";
import { ExtensionsView } from "./sections/ExtensionsView";
import { PluginsView } from "./sections/PluginsView";
import { useCorvus, type Section } from "./state/store";
import { applyThemeVars } from "./lib/theme";
import { api } from "./lib/api";

// Fluent brand ramp anchored on the electric-blue accent token.
const corvusBrand: BrandVariants = {
  10: "#020308", 20: "#0B1220", 30: "#12224A", 40: "#1B3A80",
  50: "#234A9E", 60: "#2E5FC7", 70: "#3B72E3", 80: "#4F8CFF",
  90: "#639AFF", 100: "#7AAAFF", 110: "#8FB8FF", 120: "#A5C6FF",
  130: "#BBD4FF", 140: "#D1E2FF", 150: "#E7F0FF", 160: "#F3F8FF",
};
const darkTheme = createDarkTheme(corvusBrand);
const lightTheme = createLightTheme(corvusBrand);

const SECTIONS: Record<Section, () => JSX.Element> = {
  chat: ChatView,
  history: HistoryView,
  memory: MemoryView,
  settings: SettingsView,
  logs: LogsView,
  tasks: TasksView,
  extensions: ExtensionsView,
  downloads: DownloadsView,
  plugins: PluginsView,
};

export default function App() {
  const theme = useCorvus((s) => s.theme);
  const section = useCorvus((s) => s.section);
  const setBackendOnline = useCorvus((s) => s.setBackendOnline);
  const newConversation = useCorvus((s) => s.newConversation);
  const voiceMode = useCorvus((s) => s.voiceMode);
  const backendOnline = useCorvus((s) => s.backendOnline);
  const connectVoiceSocket = useCorvus((s) => s.connectVoiceSocket);
  const Body = SECTIONS[section];

  // Keep the voice socket up whenever the backend is reachable, so a wake
  // word can summon voice mode even while the user is typing.
  useEffect(() => {
    if (backendOnline) connectVoiceSocket();
  }, [backendOnline, connectVoiceSocket]);

  // Crash recovery: restore the conversation we were in, once per launch.
  const restored = useRef(false);
  useEffect(() => {
    if (!backendOnline || restored.current) return;
    restored.current = true;
    void (async () => {
      const s = await api.session();
      if (s.active_conversation != null) {
        await useCorvus.getState().openConversation(s.active_conversation);
      }
      if (s.recovered) {
        try {
          if ("Notification" in window)
            new Notification("Corvus recovered", {
              body: "Picked up after an unexpected shutdown — your history is intact.",
            });
        } catch {
          /* no notification support; recovery still happened silently */
        }
      }
    })();
  }, [backendOnline]);

  useEffect(() => applyThemeVars(theme), [theme]);

  // Backend liveness poll — drives the offline banner and input state.
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

  return (
    <FluentProvider theme={theme === "dark" ? darkTheme : lightTheme} className="h-full !bg-transparent">
      <div className="app-bg relative flex h-full flex-col">
        <NotificationsLayer />
        <AnimatePresence>{voiceMode && <VoiceMode />}</AnimatePresence>
        {/* Draggable titlebar strip (native window buttons overlay the right edge) */}
        <header className="titlebar-drag flex h-10 shrink-0 items-center gap-2 px-4">
          <img src="/logo.svg" alt="" className="h-4 w-4" />
          <span className="text-caption text-fg-muted">Corvus</span>
          <button
            onClick={() => {
              newConversation();
              useCorvus.getState().setSection("chat");
            }}
            className="titlebar-no-drag ml-4 rounded px-2 py-0.5 text-caption text-fg-muted transition-colors duration-fast hover:bg-accent/10 hover:text-fg"
          >
            + New chat
          </button>
        </header>
        <div className="flex min-h-0 flex-1 gap-4 p-4 pt-1">
          <Sidebar />
          <main className="min-w-0 flex-1">
            <Body />
          </main>
        </div>
      </div>
    </FluentProvider>
  );
}
