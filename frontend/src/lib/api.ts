/**
 * Typed client for the Corvus backend (FastAPI on 127.0.0.1:8765).
 * REST for CRUD, one WebSocket per in-flight generation for token streaming.
 */

export const BACKEND_HTTP = "http://127.0.0.1:8765";
export const BACKEND_WS = "ws://127.0.0.1:8765";

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  conversation_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Memory {
  id: number;
  category: "preference" | "project" | "person" | "app";
  content: string;
  source_conversation: number | null;
  created_at: string;
}

export interface BackendSettings {
  provider: string;
  model: string;
  tts_voice: string | null;
}

export interface VoiceStatus {
  available: boolean;
  state: string;
  wake_enabled: boolean;
  voice?: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  event: string;
  [key: string]: unknown;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_HTTP}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`Corvus backend ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: (title: string) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ title }) }),
  deleteConversation: (id: number) =>
    request<{ ok: boolean }>(`/conversations/${id}`, { method: "DELETE" }),
  listMessages: (conversationId: number) =>
    request<ChatMessage[]>(`/conversations/${conversationId}/messages`),
  listMemories: () => request<Memory[]>("/memories"),
  deleteMemory: (id: number) => request<{ ok: boolean }>(`/memories/${id}`, { method: "DELETE" }),
  exportMemoriesUrl: () => `${BACKEND_HTTP}/memories/export`,
  getSettings: () => request<BackendSettings>("/settings"),
  updateSettings: (settings: Partial<BackendSettings>) =>
    request<BackendSettings>("/settings", { method: "PATCH", body: JSON.stringify(settings) }),
  listModels: () => request<{ models: string[] }>("/models"),
  tailLogs: (limit = 200) => request<LogEntry[]>(`/logs?limit=${limit}`),
  voiceStatus: () => request<VoiceStatus>("/voice/status"),
  listActionSpecs: () => request<ActionSpec[]>("/actions"),
  actionLog: (limit = 100) => request<ActionLogEntry[]>(`/actions/log?limit=${limit}`),
  downloads: () => request<DownloadItem[]>("/downloads"),
  browserStatus: () => request<BrowserStatus>("/browser/status"),
  uploadFile: async (file: File): Promise<{ path: string; filename: string }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BACKEND_HTTP}/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`upload failed: ${res.status}`);
    return res.json();
  },
  listWorkflows: () => request<Workflow[]>("/workflows"),
  runWorkflow: (name: string) =>
    request<{ results: { action: string; ok: boolean; message: string }[] }>(
      `/workflows/${encodeURIComponent(name)}/run`,
      { method: "POST" },
    ),
  deleteWorkflow: (name: string) =>
    request<{ ok: boolean }>(`/workflows/${encodeURIComponent(name)}`, { method: "DELETE" }),
  listPlugins: () => request<Plugin[]>("/plugins"),
  enablePlugin: (id: string) =>
    request<{ loaded: boolean; error: string | null }>(`/plugins/${id}/enable`, { method: "POST" }),
  disablePlugin: (id: string) => request<{ ok: boolean }>(`/plugins/${id}/disable`, { method: "POST" }),
  setPluginPermissions: (id: string, permissions: string[]) =>
    request<{ ok: boolean; granted: string[] }>(`/plugins/${id}/permissions`, {
      method: "PUT",
      body: JSON.stringify({ permissions }),
    }),
  listProviders: () => request<ProviderInfo[]>("/providers"),
  setProviderKey: (provider: string, key: string) =>
    request<{ ok: boolean; has_key: boolean }>("/providers/key", {
      method: "PUT",
      body: JSON.stringify({ provider, key }),
    }),
  clearProviderKey: (provider: string) =>
    request<{ ok: boolean }>(`/providers/key/${provider}`, { method: "DELETE" }),
};

export interface Plugin {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  permissions: string[];
  enabled: boolean;
  granted_permissions: string[];
  loaded: boolean;
  actions: string[];
  error: string | null;
  bundled: boolean;
}

export interface WorkflowStep {
  action: string;
  arguments: Record<string, unknown>;
}

export interface Workflow {
  id: number;
  name: string;
  steps: WorkflowStep[];
  trigger_type: "manual" | "schedule" | "voice";
  trigger_config: { at?: string; phrase?: string };
  enabled: boolean;
}

export interface ProviderInfo {
  name: string;
  label: string;
  needs_key: boolean;
  has_key: boolean;
  default_model: string;
  key_url: string;
}

export type NotificationEvent =
  | { type: "notify"; title: string; message: string; level: string }
  | { type: "reminder"; id: number; kind: string; title: string; message: string };

/** Long-lived socket for desktop notifications and reminder fires. */
export function connectNotifications(
  onEvent: (event: NotificationEvent) => void,
  onClose: () => void,
): { close: () => void } {
  const ws = new WebSocket(`${BACKEND_WS}/ws/notifications`);
  ws.onmessage = (e) => onEvent(JSON.parse(e.data) as NotificationEvent);
  ws.onclose = onClose;
  ws.onerror = () => ws.close();
  return { close: () => ws.close() };
}

export interface DownloadItem {
  filename: string;
  path: string;
  url: string;
  created_at: string;
}

export interface BrowserStatus {
  available: boolean;
  open: boolean;
  consented_sites?: string[];
  downloads?: number;
}

export type VoiceEvent =
  | { type: "state"; state: "idle" | "listening" | "thinking" | "speaking"; conversation_id: number | null }
  | { type: "level"; value: number }
  | { type: "wake" }
  | { type: "transcript"; text: string }
  | { type: "assistant_delta"; text: string }
  | { type: "assistant_done"; conversation_id: number }
  | { type: "wake_enabled"; enabled: boolean }
  | { type: "unavailable"; reason: string }
  | { type: "error"; message: string };

export type VoiceCommand =
  | { type: "ptt" }
  | { type: "set_wake"; enabled: boolean }
  | { type: "stop" };

export interface VoiceSocket {
  send: (command: VoiceCommand) => void;
  close: () => void;
}

/** Long-lived voice event socket; the caller owns reconnection policy. */
export function connectVoice(
  onEvent: (event: VoiceEvent) => void,
  onClose: () => void,
): VoiceSocket {
  const ws = new WebSocket(`${BACKEND_WS}/ws/voice`);
  ws.onmessage = (event) => onEvent(JSON.parse(event.data) as VoiceEvent);
  ws.onclose = onClose;
  ws.onerror = () => ws.close();
  return {
    send: (command) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(command));
    },
    close: () => ws.close(),
  };
}

export type RiskTier = "safe" | "low" | "medium" | "high";

export type StreamFrame =
  | { type: "start"; conversation_id: number; user_message_id: number }
  | { type: "delta"; content: string }
  | { type: "action_proposed"; name: string; arguments: Record<string, unknown>; risk: RiskTier; category: string }
  | { type: "action_confirming"; name: string; prompt: string; risk: RiskTier }
  | { type: "action_result"; name: string; ok: boolean; message: string; declined?: boolean; data?: Record<string, unknown> }
  | { type: "done"; message_id: number; conversation_id: number }
  | { type: "error"; message: string };

export interface StreamHandle {
  cancel: () => void;
  confirm: (approved: boolean) => void;
}

export interface ActionSpec {
  name: string;
  description: string;
  risk: RiskTier;
  category: string;
  requires_confirmation: boolean;
}

export interface ActionLogEntry {
  id: number;
  conversation_id: number | null;
  action: string;
  arguments: string;
  outcome: "executed" | "declined" | "failed";
  message: string;
  created_at: string;
}

/**
 * Stream one assistant turn. Frames arrive via onFrame; the socket closes
 * itself after done/error. cancel() asks the backend to stop generating
 * (partial output is kept and persisted server-side).
 */
export function streamChat(
  params: { conversationId: number | null; content: string },
  onFrame: (frame: StreamFrame) => void,
  onClose: () => void,
): StreamHandle {
  const ws = new WebSocket(`${BACKEND_WS}/ws/chat`);
  ws.onopen = () =>
    ws.send(
      JSON.stringify({
        type: "start",
        conversation_id: params.conversationId,
        content: params.content,
      }),
    );
  ws.onmessage = (event) => onFrame(JSON.parse(event.data) as StreamFrame);
  ws.onerror = () => onFrame({ type: "error", message: "Connection to the Corvus backend failed." });
  ws.onclose = onClose;
  const send = (msg: object) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };
  return {
    cancel: () => send({ type: "cancel" }),
    confirm: (approved: boolean) => send({ type: "confirm", approved }),
  };
}
