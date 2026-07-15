import { useCorvus, type Section } from "../state/store";
import {
  MessageSquare,
  Clock,
  Brain,
  CheckSquare,
  Settings,
  Blocks,
  Download,
  ScrollText,
  Plug
} from "lucide-react";

interface Item {
  key: Section;
  label: string;
  icon: React.ReactNode;
}

const ITEMS: Item[] = [
  { key: "chat", label: "Chat", icon: <MessageSquare className="h-4 w-4" /> },
  { key: "history", label: "History", icon: <Clock className="h-4 w-4" /> },
  { key: "memory", label: "Memory", icon: <Brain className="h-4 w-4" /> },
  { key: "tasks", label: "Tasks", icon: <CheckSquare className="h-4 w-4" /> },
  { key: "settings", label: "Settings", icon: <Settings className="h-4 w-4" /> },
  { key: "extensions", label: "Extensions", icon: <Blocks className="h-4 w-4" /> },
  { key: "downloads", label: "Downloads", icon: <Download className="h-4 w-4" /> },
  { key: "logs", label: "Logs", icon: <ScrollText className="h-4 w-4" /> },
  { key: "plugins", label: "Plugins", icon: <Plug className="h-4 w-4" /> },
];

export function Sidebar() {
  const section = useCorvus((s) => s.section);
  const setSection = useCorvus((s) => s.setSection);
  const backendOnline = useCorvus((s) => s.backendOnline);

  return (
    <nav className="glass flex h-full w-56 flex-col rounded-lg p-3" aria-label="Corvus sections">
      <div className="mb-4 flex items-center gap-2 px-2 pt-1">
        <img src="./logo.png" alt="" className="h-8 w-8" />
        <span className="text-h4 tracking-tight">Corvus</span>
      </div>
      <ul className="flex flex-1 flex-col gap-1">
        {ITEMS.map((item) => (
          <li key={item.key}>
            <button
              onClick={() => setSection(item.key)}
              aria-current={section === item.key ? "page" : undefined}
              className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-body transition-colors duration-fast ${
                section === item.key
                  ? "bg-accent/20 text-fg shadow-glow"
                  : "text-fg-muted hover:bg-accent/10 hover:text-fg"
              }`}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2 px-3 py-2 text-caption text-fg-faint">
        <span
          className={`h-2 w-2 rounded-full ${backendOnline ? "bg-success" : "bg-danger"}`}
          aria-hidden
        />
        {backendOnline ? "Corvus core online" : "Corvus core offline"}
      </div>
    </nav>
  );
}
