import { useCorvus, type Section } from "../state/store";

interface Item {
  key: Section;
  label: string;
  icon: string;
}

const ITEMS: Item[] = [
  { key: "chat", label: "Chat", icon: "💬" },
  { key: "history", label: "History", icon: "🕘" },
  { key: "memory", label: "Memory", icon: "🧠" },
  { key: "tasks", label: "Tasks", icon: "✅" },
  { key: "settings", label: "Settings", icon: "⚙️" },
  { key: "extensions", label: "Extensions", icon: "🧩" },
  { key: "downloads", label: "Downloads", icon: "📥" },
  { key: "logs", label: "Logs", icon: "📜" },
  { key: "plugins", label: "Plugins", icon: "🔌" },
];

export function Sidebar() {
  const section = useCorvus((s) => s.section);
  const setSection = useCorvus((s) => s.setSection);
  const backendOnline = useCorvus((s) => s.backendOnline);

  return (
    <nav className="glass flex h-full w-56 flex-col rounded-lg p-3" aria-label="Corvus sections">
      <div className="mb-4 flex items-center gap-2 px-2 pt-1">
        <img src="/logo.svg" alt="" className="h-6 w-6" />
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
