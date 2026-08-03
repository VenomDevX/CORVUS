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
  | "studio"
  | "history"
  | "tasks"
  | "settings"
  | "extensions"
  | "downloads"
  | "plugins";

export type Theme = "dark" | "light" | "system" | "pink" | "green" | "blue" | "purple";
export type AccentColor = "monochrome" | "blue" | "emerald" | "amethyst" | "amber" | "ruby" | "ocean" | "cyberpunk" | "forest" | "blush" | "neon" | "midnight" | "black";
export type UiScale = "compact" | "default" | "large";
export type FontFamily = "system" | "monospace" | "serif" | "comic";
export type UiRoundness = "sharp" | "default" | "rounded" | "pill";
export type AppOpacity = "solid" | "glassy" | "transparent";
export type AnimationSpeed = "fast" | "default" | "slow";

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
  id?: string | number;
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
const ACCENT_KEY = "corvus.accent";
const SCALE_KEY = "corvus.scale";
const FONT_KEY = "corvus.font";
const ROUNDNESS_KEY = "corvus.roundness";
const OPACITY_KEY = "corvus.opacity";
const ANIMATION_KEY = "corvus.animation";
const SIDEBAR_MIN_KEY = "corvus.sidebar_minimized";

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
  accentColor: AccentColor;
  uiScale: UiScale;
  fontFamily: FontFamily;
  uiRoundness: UiRoundness;
  appOpacity: AppOpacity;
  animationSpeed: AnimationSpeed;
  sidebarMinimized: boolean;
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
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;

  setTheme: (theme: Theme) => void;
  setAccentColor: (color: AccentColor) => void;
  setUiScale: (scale: UiScale) => void;
  setFontFamily: (font: FontFamily) => void;
  setUiRoundness: (roundness: UiRoundness) => void;
  setAppOpacity: (opacity: AppOpacity) => void;
  setAnimationSpeed: (speed: AnimationSpeed) => void;
  setSidebarMinimized: (minimized: boolean) => void;
  setSection: (section: Section) => void;
  setBackendOnline: (online: boolean) => void;
  refreshConversations: () => Promise<void>;
  openConversation: (id: number) => Promise<void>;
  newConversation: () => void;
  send: (content: string, editMessageId?: number) => void;
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

export const useCorvus = create<CorvusStore>()((set, get) => ({
  theme: (localStorage.getItem(THEME_KEY) as Theme) || "dark",
  accentColor: (localStorage.getItem(ACCENT_KEY) as AccentColor) || "monochrome",
  uiScale: (localStorage.getItem(SCALE_KEY) as UiScale) || "default",
  fontFamily: (localStorage.getItem(FONT_KEY) as FontFamily) || "system",
  uiRoundness: (localStorage.getItem(ROUNDNESS_KEY) as UiRoundness) || "default",
  appOpacity: (localStorage.getItem(OPACITY_KEY) as AppOpacity) || "glassy",
  animationSpeed: (localStorage.getItem(ANIMATION_KEY) as AnimationSpeed) || "default",
  sidebarMinimized: localStorage.getItem(SIDEBAR_MIN_KEY) === "true",
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
  paletteOpen: false,
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
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
  setAccentColor: (accentColor) => {
    localStorage.setItem(ACCENT_KEY, accentColor);
    document.documentElement.dataset.accent = accentColor;
    set({ accentColor });
  },
  setUiScale: (uiScale) => {
    localStorage.setItem(SCALE_KEY, uiScale);
    document.documentElement.dataset.scale = uiScale;
    set({ uiScale });
  },
  setFontFamily: (fontFamily) => {
    localStorage.setItem(FONT_KEY, fontFamily);
    document.documentElement.dataset.font = fontFamily;
    set({ fontFamily });
  },
  setUiRoundness: (uiRoundness) => {
    localStorage.setItem(ROUNDNESS_KEY, uiRoundness);
    document.documentElement.dataset.roundness = uiRoundness;
    set({ uiRoundness });
  },
  setAppOpacity: (appOpacity) => {
    localStorage.setItem(OPACITY_KEY, appOpacity);
    document.documentElement.dataset.opacity = appOpacity;
    set({ appOpacity });
  },
  setAnimationSpeed: (animationSpeed) => {
    localStorage.setItem(ANIMATION_KEY, animationSpeed);
    document.documentElement.dataset.animation = animationSpeed;
    set({ animationSpeed });
  },
  setSidebarMinimized: (sidebarMinimized) => {
    localStorage.setItem(SIDEBAR_MIN_KEY, String(sidebarMinimized));
    set({ sidebarMinimized });
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

  send: (content, editMessageId) => {
    const { generating, conversationId } = get();
    if (generating || !content.trim()) return;

    if (editMessageId !== undefined) {
      set((s) => {
        const idx = s.messages.findIndex(m => m.id === editMessageId);
        if (idx === -1) return s;
        const messages = s.messages.slice(0, idx + 1);
        messages[idx] = { ...messages[idx], content };
        return {
          messages: [...messages, { id: crypto.randomUUID(), role: "assistant", content: "" }],
          generating: true,
          orbState: orbStateFor({ generating: true, listening: false, speaking: false }),
        };
      });
    } else {
      set((s) => ({
        messages: [...s.messages, { id: crypto.randomUUID(), role: "user", content }, { id: crypto.randomUUID(), role: "assistant", content: "" }],
        generating: true,
        orbState: orbStateFor({ generating: true, listening: false, speaking: false }),
      }));
    }

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

    const handle = streamChat({ conversationId, content, editMessageId }, (frame) => {
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
          upsertAction(frame.name, { status: "confirming", prompt: frame.prompt, risk: frame.risk });
          set({ pendingConfirmation: { name: frame.name, prompt: frame.prompt, risk: frame.risk } });
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
document.documentElement.dataset.accent = (localStorage.getItem(ACCENT_KEY) as AccentColor) ?? "monochrome";
document.documentElement.dataset.scale = (localStorage.getItem(SCALE_KEY) as UiScale) ?? "default";
document.documentElement.dataset.font = (localStorage.getItem(FONT_KEY) as FontFamily) ?? "system";
document.documentElement.dataset.roundness = (localStorage.getItem(ROUNDNESS_KEY) as UiRoundness) ?? "default";
document.documentElement.dataset.opacity = (localStorage.getItem(OPACITY_KEY) as AppOpacity) ?? "glassy";
document.documentElement.dataset.animation = (localStorage.getItem(ANIMATION_KEY) as AnimationSpeed) ?? "default";
