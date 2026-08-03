import { motion } from "framer-motion";
import { useCorvus, type Section } from "../state/store";
import {
  MessageSquare,
  AudioLines,
  Clock,
  CheckSquare,
  Settings,
  Blocks,
  Download,
  Plug,
  ChevronLeft,
  ChevronRight
} from "lucide-react";

interface Item {
  key: Section;
  label: string;
  icon: React.ReactNode;
}

export const NAV_ITEMS: Item[] = [
  { key: "chat", label: "Chat", icon: <MessageSquare className="h-4 w-4" /> },
  { key: "studio", label: "Voice Studio", icon: <AudioLines className="h-4 w-4" /> },
  { key: "history", label: "History", icon: <Clock className="h-4 w-4" /> },
  { key: "tasks", label: "Tasks", icon: <CheckSquare className="h-4 w-4" /> },
  { key: "extensions", label: "Extensions", icon: <Blocks className="h-4 w-4" /> },
  { key: "downloads", label: "Downloads", icon: <Download className="h-4 w-4" /> },
  { key: "plugins", label: "Plugins", icon: <Plug className="h-4 w-4" /> },
];

export function Sidebar() {
  const section = useCorvus((s) => s.section);
  const setSection = useCorvus((s) => s.setSection);
  const sidebarMinimized = useCorvus((s) => s.sidebarMinimized);
  const setSidebarMinimized = useCorvus((s) => s.setSidebarMinimized);

  return (
    <nav 
      className={`liquid-glass flex h-full flex-col rounded-md p-3 transition-all duration-300 overflow-hidden ${sidebarMinimized ? "w-[68px]" : "w-56"}`} 
      aria-label="Corvus sections"
    >
      <div className={`mb-4 flex items-center ${sidebarMinimized ? 'gap-1' : 'justify-between'} px-1 pt-1 overflow-hidden`}>
        <div className="flex items-center gap-2 overflow-hidden">
          <img src="./logo.png" alt="" className={`h-6 w-6 shrink-0 ${sidebarMinimized ? '-ml-1' : ''}`} />
          {!sidebarMinimized && <span className="text-h4 tracking-tight whitespace-nowrap">Corvus</span>}
        </div>
        <button
          onClick={() => setSidebarMinimized(!sidebarMinimized)}
          className={`rounded text-fg-muted hover:bg-white/10 hover:text-fg transition-colors shrink-0 ${sidebarMinimized ? 'p-0.5' : 'p-1'}`}
          title={sidebarMinimized ? "Expand Sidebar" : "Minimize Sidebar"}
        >
          {sidebarMinimized ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
      <ul className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.key}>
            <button
              onClick={() => setSection(item.key)}
              aria-current={section === item.key ? "page" : undefined}
              className={`relative flex w-full items-center gap-3 rounded px-3 py-2 text-left text-body transition-colors duration-fast ${
                section === item.key ? "text-fg" : "text-fg-muted hover:bg-white/5 hover:text-fg"
              }`}
            >
              {section === item.key && (
                <motion.span
                  layoutId="nav-pill"
                  className="absolute inset-0 rounded bg-white/10"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                  aria-hidden
                />
              )}
              <span aria-hidden className="relative shrink-0">{item.icon}</span>
              {!sidebarMinimized && <span className="relative whitespace-nowrap">{item.label}</span>}
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-auto flex flex-col gap-1">
        <button
          onClick={() => setSection("settings")}
          aria-current={section === "settings" ? "page" : undefined}
          className={`relative flex w-full items-center gap-3 rounded px-3 py-2 text-left text-body transition-colors duration-fast ${
            section === "settings" ? "text-fg" : "text-fg-muted hover:bg-white/5 hover:text-fg"
          }`}
        >
          {section === "settings" && (
            <motion.span
              layoutId="nav-pill"
              className="absolute inset-0 rounded bg-white/10"
              transition={{ type: "spring", stiffness: 500, damping: 40 }}
              aria-hidden
            />
          )}
          <span aria-hidden className="relative shrink-0"><Settings className="h-4 w-4" /></span>
          {!sidebarMinimized && <span className="relative whitespace-nowrap">Settings</span>}
        </button>
      </div>
    </nav>
  );
}
