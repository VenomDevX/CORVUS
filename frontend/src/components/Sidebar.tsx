import { useEffect } from "react";
import { motion } from "framer-motion";
import { useCorvus, type Section } from "../state/store";
import {
  MessageSquare,
  AudioLines,
  Clock,
  CheckSquare,
  Settings,
  Plug,
  Plus,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

interface Item {
  key: Section;
  label: string;
  icon: React.ReactNode;
}

export const NAV_ITEMS: Item[] = [
  { key: "chat", label: "Chat", icon: <MessageSquare className="h-4 w-4" /> },
  { key: "history", label: "History", icon: <Clock className="h-4 w-4" /> },
  { key: "tasks", label: "Tasks", icon: <CheckSquare className="h-4 w-4" /> },
  { key: "studio", label: "Studio", icon: <AudioLines className="h-4 w-4" /> },
  { key: "plugins", label: "Plugins", icon: <Plug className="h-4 w-4" /> },
];

const RECENT_CHATS = 10;

function NavButton({ item, active, mini, onClick }: { item: Item; active: boolean; mini: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={mini ? item.label : undefined}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      className={`relative flex w-full items-center gap-3 rounded px-3 py-2 text-left text-body transition-colors duration-fast ${
        active ? "text-fg" : "text-fg-muted hover:bg-white/5 hover:text-fg"
      }`}
    >
      {active && (
        <motion.span
          layoutId="nav-pill"
          className="absolute inset-0 rounded bg-white/10"
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
          aria-hidden
        />
      )}
      <span aria-hidden className="relative shrink-0">{item.icon}</span>
      {!mini && <span className="relative whitespace-nowrap">{item.label}</span>}
    </button>
  );
}

export function Sidebar() {
  const section = useCorvus((s) => s.section);
  const setSection = useCorvus((s) => s.setSection);
  const sidebarMinimized = useCorvus((s) => s.sidebarMinimized);
  const setSidebarMinimized = useCorvus((s) => s.setSidebarMinimized);
  const conversations = useCorvus((s) => s.conversations);
  const conversationId = useCorvus((s) => s.conversationId);
  const refreshConversations = useCorvus((s) => s.refreshConversations);
  const openConversation = useCorvus((s) => s.openConversation);
  const newConversation = useCorvus((s) => s.newConversation);
  const backendOnline = useCorvus((s) => s.backendOnline);
  // Settings has its own nav column; collapsing ours gives the content room.
  const mini = sidebarMinimized || section === "settings";

  useEffect(() => {
    if (backendOnline) void refreshConversations().catch(() => undefined);
  }, [backendOnline, refreshConversations]);

  const recent = [...conversations]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, RECENT_CHATS);

  return (
    <nav
      className={`flex h-full flex-col border-r border-white/5 bg-white/[0.02] p-3 transition-all duration-300 overflow-hidden ${mini ? "w-[68px]" : "w-60"}`}
      aria-label="Corvus sections"
    >
      <div className={`mb-3 flex items-center ${mini ? "justify-center" : "justify-between"} px-1 pt-1`}>
        {!mini && (
          <div className="flex items-center gap-2 overflow-hidden">
            <img src="./logo.png" alt="" className="h-5 w-5 shrink-0" />
            <span className="text-h4 tracking-tight whitespace-nowrap">Corvus</span>
          </div>
        )}
        <button
          onClick={() => setSidebarMinimized(!sidebarMinimized)}
          disabled={section === "settings"}
          className="rounded p-1 text-fg-muted transition-colors hover:bg-white/10 hover:text-fg disabled:opacity-40"
          title={mini ? "Expand sidebar" : "Minimize sidebar"}
          aria-label={mini ? "Expand sidebar" : "Minimize sidebar"}
        >
          {mini ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      <button
        onClick={() => {
          newConversation();
          setSection("chat");
        }}
        title="New chat"
        aria-label="New chat"
        className="mb-3 flex w-full items-center justify-center gap-2 rounded bg-accent/15 px-3 py-2 text-body text-fg transition-colors duration-fast hover:bg-accent/25"
      >
        <Plus className="h-4 w-4 shrink-0" />
        {!mini && <span className="whitespace-nowrap">New chat</span>}
      </button>

      <ul className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.key}>
            <NavButton item={item} active={section === item.key} mini={mini} onClick={() => setSection(item.key)} />
          </li>
        ))}
      </ul>

      {!mini && recent.length > 0 && (
        <div className="mt-4 flex min-h-0 flex-1 flex-col">
          <h2 className="mb-1 px-3 text-caption uppercase tracking-wide text-fg-faint">Recent</h2>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {recent.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => void openConversation(c.id)}
                  title={c.title}
                  className={`w-full truncate rounded px-3 py-1.5 text-left text-body-sm transition-colors duration-fast ${
                    section === "chat" && conversationId === c.id
                      ? "bg-white/10 text-fg"
                      : "text-fg-muted hover:bg-white/5 hover:text-fg"
                  }`}
                >
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-auto pt-2">
        <NavButton
          item={{ key: "settings", label: "Settings", icon: <Settings className="h-4 w-4" /> }}
          active={section === "settings"}
          mini={mini}
          onClick={() => setSection("settings")}
        />
      </div>
    </nav>
  );
}
