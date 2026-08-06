import { useState, useEffect, useRef } from "react";
import {
  FluentProvider,
  createDarkTheme,
  createLightTheme,
  type BrandVariants,
} from "@fluentui/react-components";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./components/Sidebar";
import { ChatView } from "./components/ChatView";
import { VoiceMode } from "./components/VoiceMode";
import { Menu } from "lucide-react";
import { NotificationsLayer } from "./components/NotificationsLayer";
import { CommandPalette } from "./components/CommandPalette";
import { OnboardingSetup } from "./components/OnboardingSetup";
import { ThinkingAnimation } from "./components/ThinkingAnimation";
import { HistoryView } from "./sections/HistoryView";
import { StudioView } from "./sections/StudioView";
import { SettingsView } from "./sections/SettingsView";
import { TasksView } from "./sections/TasksView";
import { DownloadsView } from "./sections/DownloadsView";
import { ExtensionsView } from "./sections/ExtensionsView";
import { PluginsView } from "./sections/PluginsView";
import { useCorvus, type Section } from "./state/store";
import { applyThemeVars } from "./lib/theme";
import { api } from "./lib/api";

// Fluent brand ramp anchored on the electric-blue accent token.
const corvusBrand: BrandVariants = {
  10: "#050505", 20: "#111111", 30: "#222222", 40: "#333333",
  50: "#444444", 60: "#555555", 70: "#777777", 80: "#999999",
  90: "#BBBBBB", 100: "#DDDDDD", 110: "#EEEEEE", 120: "#F5F5F5",
  130: "#FAFAFA", 140: "#FCFCFC", 150: "#FEFEFE", 160: "#FFFFFF",
};
const darkTheme = createDarkTheme(corvusBrand);
const lightTheme = createLightTheme(corvusBrand);

const SECTIONS: Record<Section, () => JSX.Element> = {
  chat: ChatView,
  studio: StudioView,
  history: HistoryView,
  settings: SettingsView,
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
  const accentColor = useCorvus((s) => s.accentColor);
  const fontFamily = useCorvus((s) => s.fontFamily);
  const uiRoundness = useCorvus((s) => s.uiRoundness);
  const appOpacity = useCorvus((s) => s.appOpacity);
  const animationSpeed = useCorvus((s) => s.animationSpeed);
  const backendOnline = useCorvus((s) => s.backendOnline);
  const uiScale = useCorvus((s) => s.uiScale);
  const connectVoiceSocket = useCorvus((s) => s.connectVoiceSocket);
  const Body = SECTIONS[section];
  
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // null = not yet known (don't flash the wizard); persisted in backend settings.
  const [onboardingComplete, setOnboardingComplete] = useState<boolean | null>(null);
  useEffect(() => {
    if (!backendOnline || onboardingComplete !== null) return;
    void api
      .getSettings()
      .then((s) => setOnboardingComplete(s.onboarding_complete))
      .catch(() => undefined);
  }, [backendOnline, onboardingComplete]);

  // Keep the voice socket up whenever the backend is reachable, so a wake
  // word can summon voice mode even while the user is typing.
  useEffect(() => {
    if (backendOnline) connectVoiceSocket();
  }, [backendOnline, connectVoiceSocket]);

  // Check session on launch, but start a fresh chat by default.
  const restored = useRef(false);
  useEffect(() => {
    if (!backendOnline || restored.current) return;
    restored.current = true;
    void (async () => {
      const s = await api.session();
      // We no longer restore active_conversation on startup.
      // The user will start with a fresh chat, and previous chats remain in history.
      
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

  useEffect(() => {
    // Automatically check for updates in the background and show a Toast.
    const off = window.corvus?.onUpdateStatus?.((status) => {
      if (status.state === "available") {
        try {
          if ("Notification" in window) {
            new Notification("Corvus Update Available", {
              body: `Version ${status.version} is ready. Go to Settings > About to download and install.`,
            });
          }
        } catch {
          // ignore if no native notification support
        }
      }
    });
    
    // Trigger a silent check 5 seconds after startup.
    const timer = setTimeout(() => {
      void window.corvus?.checkForUpdates?.();
    }, 5000);

    return () => {
      off?.();
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => applyThemeVars({ theme, accentColor, fontFamily, uiRoundness, appOpacity, animationSpeed, uiScale }), [theme, accentColor, fontFamily, uiRoundness, appOpacity, animationSpeed, uiScale]);

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
        {!backendOnline && (
          <div className="absolute inset-0 z-[100] flex flex-col items-center justify-center bg-[#000000]">
            <ThinkingAnimation text={null} className="h-16 w-20 text-white" containerClassName="" />
          </div>
        )}
        {onboardingComplete === false && (
          <OnboardingSetup onComplete={() => setOnboardingComplete(true)} />
        )}
        <NotificationsLayer />
        <CommandPalette />
        <AnimatePresence>{voiceMode && <VoiceMode />}</AnimatePresence>
        {/* Draggable titlebar strip (native window buttons overlay the right edge) */}
        <header className="titlebar-drag flex h-10 shrink-0 items-center gap-2 px-4">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="titlebar-no-drag rounded p-1 text-fg-muted hover:bg-white/5 hover:text-fg md:hidden"
          >
            <Menu className="h-4 w-4" />
          </button>
          <img src="./logo.png" alt="" className="h-4 w-4 hidden md:block" />
          <span className="text-caption text-fg-muted hidden md:inline">Corvus</span>
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
          <div className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-300 md:relative md:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} ${onboardingComplete === false ? "hidden" : ""}`}>
            <Sidebar />
          </div>
          {sidebarOpen && (
            <div 
              className="fixed inset-0 z-40 bg-black/20 md:hidden" 
              onClick={() => setSidebarOpen(false)}
            />
          )}
          <main className="min-w-0 flex-1 max-w-full">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={section}
                className="h-full"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.12, ease: "easeOut" }}
              >
                <Body />
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </div>
    </FluentProvider>
  );
}
