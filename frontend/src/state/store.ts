import { create } from "zustand";
import {
  api,
  connectVoice,
  streamChat,
  type ChatMessage,
  type Conversation,
  type RiskTier,
  type StreamHandle,
  type VoiceSocket,
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

export interface ActionEvent {
  name: string;
  arguments: Record<string, unknown>;
  risk: RiskTier;
  category: string;
  status: "proposed" | "confirming" | "ok" | "failed" | "declined";
  message?: string;
  prompt?: string;
}

/** Local (not yet persisted) rendering of an in-flight assistant turn. */
export interface DraftMessage {
  role: "user" | "assistant";
  content: string;
  attachments?: { name: string; size: number; type: string; url?: string }[];
  actions?: ActionEvent[];
}

export interface PendingConfirmation {
  name: string;
  prompt: string;
  risk: RiskTier;
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

interface VoiceState {
  connected: boolean;
  available: boolean;
  wakeEnabled: boolean;
  level: number;
  transcript: string;
  assistantLive: string;
  error: string | null;
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
  pendingConfirmation: PendingConfirmation | null;
  voiceMode: boolean;
  voice: VoiceState;

  setTheme: (theme: Theme) => void;
  setSection: (section: Section) => void;
  setBackendOnline: (online: boolean) => void;
  refreshConversations: () => Promise<void>;
  openConversation: (id: number) => Promise<void>;
  newConversation: () => void;
  send: (content: string) => void;
  stopGeneration: () => void;
  answerConfirmation: (approved: boolean) => void;
  setVoiceMode: (on: boolean) => void;
  connectVoiceSocket: () => void;
  pushToTalk: () => void;
  setWakeEnabled: (enabled: boolean) => void;
  stopSpeaking: () => void;
}

let voiceSocket: VoiceSocket | null = null;
let voiceReconnectTimer: ReturnType<typeof setTimeout> | null = null;

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
  pendingConfirmation: null,
  voiceMode: false,
  voice: {
    connected: false,
    available: false,
    wakeEnabled: false,
    level: 0.5,
    transcript: "",
    assistantLive: "",
    error: null,
  },

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

    const patchLast = (fn: (m: ChatMessage | DraftMessage) => ChatMessage | DraftMessage) =>
      set((s) => {
        const messages = [...s.messages];
        messages[messages.length - 1] = fn(messages[messages.length - 1]);
        return { messages };
      });

    const appendDelta = (delta: string) =>
      patchLast((last) => ({ ...last, content: last.content + delta }));

    const upsertAction = (name: string, patch: Partial<ActionEvent>) =>
      patchLast((last) => {
        const actions = [...((last as DraftMessage).actions ?? [])];
        const idx = actions.findIndex((a) => a.name === name && a.status !== "ok" && a.status !== "failed" && a.status !== "declined");
        if (idx >= 0) actions[idx] = { ...actions[idx], ...patch };
        else actions.push({ name, arguments: {}, risk: "low", category: "", status: "proposed", ...patch });
        return { ...last, actions };
      });

    const handle = streamChat({ conversationId, content }, (frame) => {
      switch (frame.type) {
        case "start":
          set({ conversationId: frame.conversation_id });
          break;
        case "delta":
          appendDelta(frame.content);
          break;
        case "action_proposed":
          upsertAction(frame.name, {
            arguments: frame.arguments,
            risk: frame.risk,
            category: frame.category,
            status: "proposed",
          });
          break;
        case "action_confirming":
          upsertAction(frame.name, { status: "confirming", prompt: frame.prompt });
          set({ pendingConfirmation: { name: frame.name, prompt: frame.prompt, risk: "high" } });
          break;
        case "action_result":
          upsertAction(frame.name, {
            status: frame.declined ? "declined" : frame.ok ? "ok" : "failed",
            message: frame.message,
          });
          if (get().pendingConfirmation?.name === frame.name) set({ pendingConfirmation: null });
          break;
        case "error":
          appendDelta(`\n\n> ⚠️ ${frame.message}`);
          break;
      }
      if (frame.type === "done" || frame.type === "error") {
        set({
          generating: false,
          stream: null,
          pendingConfirmation: null,
          orbState: orbStateFor({ generating: false, listening: false, speaking: false }),
        });
        void get().refreshConversations();
      }
    }, () => {
      // Socket closed without a done frame (backend crash/network drop).
      if (get().generating) {
        set({ generating: false, stream: null, pendingConfirmation: null, orbState: "idle" });
      }
    });
    set({ stream: handle });
  },

  stopGeneration: () => {
    get().stream?.cancel();
  },

  answerConfirmation: (approved) => {
    get().stream?.confirm(approved);
    set({ pendingConfirmation: null });
  },

  setVoiceMode: (on) => {
    set({ voiceMode: on });
    if (on) get().connectVoiceSocket();
  },

  connectVoiceSocket: () => {
    if (voiceSocket || !get().backendOnline) return;

    voiceSocket = connectVoice(
      (event) => {
        const patch = (v: Partial<VoiceState>) => set((s) => ({ voice: { ...s.voice, ...v } }));
        switch (event.type) {
          case "state":
            set({
              orbState: event.state,
              ...(event.conversation_id != null ? { conversationId: event.conversation_id } : {}),
            });
            patch({ connected: true, available: true });
            if (event.state === "idle") patch({ level: 0.5 });
            break;
          case "level":
            patch({ level: event.value });
            break;
          case "wake":
            // "Hey Corvus" summons the voice-first UI.
            set({ voiceMode: true });
            patch({ transcript: "", assistantLive: "" });
            break;
          case "transcript":
            patch({ transcript: event.text, assistantLive: "" });
            break;
          case "assistant_delta":
            set((s) => ({ voice: { ...s.voice, assistantLive: s.voice.assistantLive + event.text } }));
            break;
          case "assistant_done":
            void get().refreshConversations();
            break;
          case "wake_enabled":
            patch({ wakeEnabled: event.enabled });
            break;
          case "unavailable":
            patch({ available: false, error: event.reason });
            break;
          case "error":
            patch({ error: event.message });
            break;
        }
      },
      () => {
        voiceSocket = null;
        set((s) => ({ voice: { ...s.voice, connected: false }, orbState: "idle" }));
        if (voiceReconnectTimer) clearTimeout(voiceReconnectTimer);
        voiceReconnectTimer = setTimeout(() => {
          if (get().backendOnline) get().connectVoiceSocket();
        }, 3000);
      },
    );
    set((s) => ({ voice: { ...s.voice, connected: true, error: null } }));
  },

  pushToTalk: () => {
    get().connectVoiceSocket();
    set((s) => ({ voice: { ...s.voice, transcript: "", assistantLive: "" } }));
    voiceSocket?.send({ type: "ptt" });
  },

  setWakeEnabled: (enabled) => {
    voiceSocket?.send({ type: "set_wake", enabled });
  },

  stopSpeaking: () => {
    voiceSocket?.send({ type: "stop" });
  },
}));

// Apply persisted theme on load.
document.documentElement.dataset.theme = (localStorage.getItem(THEME_KEY) as Theme) ?? "dark";
