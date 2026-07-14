import { create } from "zustand";
import {
  api,
  streamChat,
  type ChatMessage,
  type Conversation,
  type StreamHandle,
} from "../lib/api";
import type { OrbState } from "../lib/tokens";

export type Section =
  | "chat"
  | "history"
  | "memory"
  | "tasks"
  | "settings"
  | "extensions"
  | "downloads"
  | "logs"
  | "plugins";

export type Theme = "dark" | "light";

/** Local (not yet persisted) rendering of an in-flight assistant turn. */
export interface DraftMessage {
  role: "user" | "assistant";
  content: string;
  attachments?: { name: string; size: number; type: string; url?: string }[];
}

const THEME_KEY = "corvus.theme";

export function orbStateFor(opts: { generating: boolean; listening: boolean; speaking: boolean }): OrbState {
  // Voice states (listening/speaking) take over in Milestone 5; text-only
  // generation maps to "thinking".
  if (opts.speaking) return "speaking";
  if (opts.listening) return "listening";
  if (opts.generating) return "thinking";
  return "idle";
}

interface CorvusStore {
  theme: Theme;
  section: Section;
  backendOnline: boolean;
  conversationId: number | null;
  conversations: Conversation[];
  messages: (ChatMessage | DraftMessage)[];
  generating: boolean;
  orbState: OrbState;
  stream: StreamHandle | null;

  setTheme: (theme: Theme) => void;
  setSection: (section: Section) => void;
  setBackendOnline: (online: boolean) => void;
  refreshConversations: () => Promise<void>;
  openConversation: (id: number) => Promise<void>;
  newConversation: () => void;
  send: (content: string) => void;
  stopGeneration: () => void;
}

export const useCorvus = create<CorvusStore>((set, get) => ({
  theme: (localStorage.getItem(THEME_KEY) as Theme) ?? "dark",
  section: "chat",
  backendOnline: false,
  conversationId: null,
  conversations: [],
  messages: [],
  generating: false,
  orbState: "idle",
  stream: null,

  setTheme: (theme) => {
    localStorage.setItem(THEME_KEY, theme);
    document.documentElement.dataset.theme = theme;
    set({ theme });
  },

  setSection: (section) => set({ section }),
  setBackendOnline: (backendOnline) => set({ backendOnline }),

  refreshConversations: async () => {
    set({ conversations: await api.listConversations() });
  },

  openConversation: async (id) => {
    const messages = await api.listMessages(id);
    set({ conversationId: id, messages, section: "chat" });
  },

  newConversation: () => set({ conversationId: null, messages: [] }),

  send: (content) => {
    const { generating, conversationId } = get();
    if (generating || !content.trim()) return;

    set((s) => ({
      messages: [...s.messages, { role: "user", content }, { role: "assistant", content: "" }],
      generating: true,
      orbState: orbStateFor({ generating: true, listening: false, speaking: false }),
    }));

    const appendDelta = (delta: string) =>
      set((s) => {
        const messages = [...s.messages];
        const last = messages[messages.length - 1];
        messages[messages.length - 1] = { ...last, content: last.content + delta };
        return { messages };
      });

    const handle = streamChat({ conversationId, content }, (frame) => {
      if (frame.type === "start") set({ conversationId: frame.conversation_id });
      if (frame.type === "delta") appendDelta(frame.content);
      if (frame.type === "error") appendDelta(`\n\n> ⚠️ ${frame.message}`);
      if (frame.type === "done" || frame.type === "error") {
        set({
          generating: false,
          stream: null,
          orbState: orbStateFor({ generating: false, listening: false, speaking: false }),
        });
        void get().refreshConversations();
      }
    }, () => {
      // Socket closed without a done frame (backend crash/network drop).
      if (get().generating) {
        set({ generating: false, stream: null, orbState: "idle" });
      }
    });
    set({ stream: handle });
  },

  stopGeneration: () => {
    get().stream?.cancel();
  },
}));

// Apply persisted theme on load.
document.documentElement.dataset.theme = (localStorage.getItem(THEME_KEY) as Theme) ?? "dark";
