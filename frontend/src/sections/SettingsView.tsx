import { useEffect, useState, useCallback } from "react";
import { Switch } from "@fluentui/react-components";
import { SectionShell } from "./SectionShell";
import { api, type Memory, type LogEntry } from "../lib/api";
import { useCorvus } from "../state/store";
import { Orb } from "../components/Orb";
import { ProviderSettings } from "../components/ProviderSettings";
import { OllamaModels } from "../components/OllamaModels";
import { DocumentsIndex } from "../components/DocumentsIndex";
import { Select } from "../components/ui/Select";
import { AboutSettings } from "../components/AboutSettings";
import { MemoryGraph } from "../components/MemoryGraph";
import { ORB_STATES, type OrbState } from "../lib/tokens";
import {
  Paintbrush,
  Info,
  Server,
  Cpu,
  FolderSearch,
  Mic,
  Volume2,
  Brain,
  ScrollText,
  Activity,
  RotateCcw,
  Search,
} from "lucide-react";

// ─── Sidebar definition ──────────────────────────────────────────────

type SettingsPage =
  | "appearance"
  | "about"
  | "providers"
  | "models"
  | "documents"
  | "wakework"
  | "ttsvoice"
  | "memory"
  | "logs"
  | "backend"
  | "setup";

interface SettingsNavItem {
  key: SettingsPage;
  label: string;
  icon: React.ReactNode;
}

interface SettingsNavGroup {
  label: string;
  items: SettingsNavItem[];
}

const SETTINGS_NAV: SettingsNavGroup[] = [
  {
    label: "GENERAL",
    items: [
      { key: "appearance", label: "Appearance", icon: <Paintbrush className="h-4 w-4" /> },
      { key: "about", label: "About & Updates", icon: <Info className="h-4 w-4" /> },
    ],
  },
  {
    label: "AI & MODELS",
    items: [
      { key: "providers", label: "Providers", icon: <Server className="h-4 w-4" /> },
      { key: "models", label: "Offline Models", icon: <Cpu className="h-4 w-4" /> },
      { key: "documents", label: "Documents Index", icon: <FolderSearch className="h-4 w-4" /> },
    ],
  },
  {
    label: "VOICE",
    items: [
      { key: "wakework", label: "Wake Word", icon: <Mic className="h-4 w-4" /> },
      { key: "ttsvoice", label: "TTS Voice", icon: <Volume2 className="h-4 w-4" /> },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { key: "memory", label: "Memory", icon: <Brain className="h-4 w-4" /> },
      { key: "logs", label: "Logs", icon: <ScrollText className="h-4 w-4" /> },
      { key: "backend", label: "Backend Status", icon: <Activity className="h-4 w-4" /> },
    ],
  },
  {
    label: "APP",
    items: [
      { key: "setup", label: "First-time Setup", icon: <RotateCcw className="h-4 w-4" /> },
    ],
  },
];

// ─── TTS voices ──────────────────────────────────────────────────────

const TTS_VOICES = [
  "en-US-AriaNeural",
  "en-US-JennyNeural",
  "en-US-MichelleNeural",
  "en-GB-SoniaNeural",
  "en-AU-NatashaNeural",
];

// ─── Log level colors ────────────────────────────────────────────────

const LEVEL_COLOR: Record<string, string> = {
  error: "text-danger",
  warning: "text-warning",
  info: "text-fg-muted",
  debug: "text-fg-faint",
};

// ─── Memory category labels ─────────────────────────────────────────

const CATEGORY_LABEL: Record<Memory["category"], string> = {
  preference: "Preference",
  project: "Project",
  person: "Person",
  app: "App",
};

// ─── Sub-page content components ────────────────────────────────────

const ACCENT_COLORS = [
  { value: "monochrome", hex: "var(--c-fg)" },
  { value: "blue", hex: "#3B82F6" },
  { value: "emerald", hex: "#10B981" },
  { value: "amethyst", hex: "#8B5CF6" },
  { value: "amber", hex: "#F59E0B" },
  { value: "ruby", hex: "#EF4444" },
  { value: "ocean", hex: "#06B6D4" },
  { value: "cyberpunk", hex: "#F472B6" },
  { value: "forest", hex: "#059669" },
  { value: "blush", hex: "#FECDD3" },
  { value: "neon", hex: "#39FF14" },
  { value: "midnight", hex: "#1E3A8A" },
  { value: "black", hex: "#000000" },
] as const;

const SCALE_MAP = ["compact", "default", "large"] as const;

function AppearancePage() {
  const theme = useCorvus((s) => s.theme);
  const setTheme = useCorvus((s) => s.setTheme);
  const accentColor = useCorvus((s) => s.accentColor);
  const setAccentColor = useCorvus.getState().setAccentColor;
  const uiScale = useCorvus((s) => s.uiScale);
  const setUiScale = useCorvus.getState().setUiScale;
  const [orbPreview, setOrbPreview] = useState<OrbState>("idle");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="mb-2 text-h3 tracking-tight font-medium">Appearance</h2>
        <p className="text-body text-fg-muted mb-6">Choose how Corvus looks on this device.</p>
        
        <div className="mb-8 flex flex-wrap gap-4">
          <button
            onClick={() => setTheme("dark")}
            className={`group flex w-48 flex-col rounded-xl border p-3 text-left transition-all duration-200 ${
              theme === "dark" || theme === "system" // fallback if system is dark
                ? "border-accent ring-2 ring-accent bg-[#1a1a1a]"
                : "border-white/10 bg-[#0a0a0a] hover:border-white/20 hover:bg-[#1a1a1a]"
            }`}
          >
            <div className="mb-3 flex h-24 w-full items-center justify-center rounded-lg border border-white/10 bg-[#0a0a0a] shadow-inner">
              <div className="h-1.5 w-10 rounded-full bg-white/20" />
            </div>
            <div className="text-[14px] font-medium text-white">Dark Theme</div>
            <div className="mt-0.5 text-[12px] text-white/60">Corvus default</div>
          </button>

          <button
            onClick={() => setTheme("light")}
            className={`group flex w-48 flex-col rounded-xl border p-3 text-left transition-all duration-200 ${
              theme === "light"
                ? "border-accent ring-2 ring-accent bg-[#e4e5e7]"
                : "border-black/10 bg-[#f4f5f7] hover:border-black/20 hover:bg-[#e4e5e7]"
            }`}
          >
            <div className="mb-3 flex h-24 w-full items-center justify-center rounded-lg border border-black/10 bg-[#f4f5f7] shadow-inner">
              <div className="h-1.5 w-10 rounded-full bg-black/20" />
            </div>
            <div className="text-[14px] font-medium text-black">Light Theme</div>
            <div className="mt-0.5 text-[12px] text-black/60">Clean and bright</div>
          </button>

          <button
            onClick={() => setTheme("pink")}
            className={`group flex w-48 flex-col rounded-xl border p-3 text-left transition-all duration-200 ${
              theme === "pink"
                ? "border-accent ring-2 ring-accent bg-[#FCE7F3]"
                : "border-[#831843]/10 bg-[#FDF2F8] hover:border-[#831843]/20 hover:bg-[#FCE7F3]"
            }`}
          >
            <div className="mb-3 flex h-24 w-full items-center justify-center rounded-lg border border-black/10 bg-[#FDF2F8] shadow-inner">
              <div className="h-1.5 w-10 rounded-full bg-[#BE185D]" />
            </div>
            <div className="text-[14px] font-medium text-[#831843]">Baby Pink</div>
            <div className="mt-0.5 text-[12px] text-[#831843]/60">Soft and warm</div>
          </button>

          <button
            onClick={() => setTheme("green")}
            className={`group flex w-48 flex-col rounded-xl border p-3 text-left transition-all duration-200 ${
              theme === "green"
                ? "border-accent ring-2 ring-accent bg-[#064E3B]"
                : "border-[#ECFDF5]/10 bg-[#022C22] hover:border-[#ECFDF5]/20 hover:bg-[#064E3B]"
            }`}
          >
            <div className="mb-3 flex h-24 w-full items-center justify-center rounded-lg border border-white/10 bg-[#022C22] shadow-inner">
              <div className="h-1.5 w-10 rounded-full bg-[#6EE7B7]" />
            </div>
            <div className="text-[14px] font-medium text-[#ECFDF5]">Green Theme</div>
            <div className="mt-0.5 text-[12px] text-[#ECFDF5]/60">Natural and dark</div>
          </button>

          <button
            onClick={() => setTheme("blue")}
            className={`group flex w-48 flex-col rounded-xl border p-3 text-left transition-all duration-200 ${
              theme === "blue"
                ? "border-accent ring-2 ring-accent bg-[#0F172A]"
                : "border-[#F8FAFC]/10 bg-[#020617] hover:border-[#F8FAFC]/20 hover:bg-[#0F172A]"
            }`}
          >
            <div className="mb-3 flex h-24 w-full items-center justify-center rounded-lg border border-white/10 bg-[#020617] shadow-inner">
              <div className="h-1.5 w-10 rounded-full bg-[#94A3B8]" />
            </div>
            <div className="text-[14px] font-medium text-[#F8FAFC]">Dark Blue</div>
            <div className="mt-0.5 text-[12px] text-[#F8FAFC]/60">Deep and moody</div>
          </button>

          <button
            onClick={() => setTheme("purple")}
            className={`group flex w-48 flex-col rounded-xl border p-3 text-left transition-all duration-200 ${
              theme === "purple"
                ? "border-accent ring-2 ring-accent bg-[#3B0764]"
                : "border-[#F5F3FF]/10 bg-[#2E1065] hover:border-[#F5F3FF]/20 hover:bg-[#3B0764]"
            }`}
          >
            <div className="mb-3 flex h-24 w-full items-center justify-center rounded-lg border border-white/10 bg-[#2E1065] shadow-inner">
              <div className="h-1.5 w-10 rounded-full bg-[#A78BFA]" />
            </div>
            <div className="text-[14px] font-medium text-[#F5F3FF]">Purple Theme</div>
            <div className="mt-0.5 text-[12px] text-[#F5F3FF]/60">Rich and mystical</div>
          </button>
        </div>
        
        <div className="grid w-full max-w-3xl grid-cols-1 md:grid-cols-2 gap-8">
          
          <div className="col-span-1 md:col-span-2">
            <label className="mb-3 block text-body-sm text-fg-muted">Accent Color</label>
            <div className="flex flex-wrap gap-3">
              {ACCENT_COLORS.map((color) => (
                <button
                  key={color.value}
                  onClick={() => setAccentColor(color.value as any)}
                  className={`h-8 w-8 rounded-xl transition-transform hover:scale-110 ${
                    accentColor === color.value ? "ring-2 ring-accent ring-offset-2 ring-offset-app" : ""
                  }`}
                  style={{ backgroundColor: color.hex }}
                  title={color.value.charAt(0).toUpperCase() + color.value.slice(1)}
                />
              ))}
            </div>
          </div>
          
          <div>
            <label className="mb-2 block text-body-sm text-fg-muted">UI Scale</label>
            <div className="px-2">
              <input
                type="range"
                min="0"
                max="2"
                step="1"
                value={SCALE_MAP.indexOf(uiScale as any)}
                onChange={(e) => setUiScale(SCALE_MAP[parseInt(e.target.value)])}
                className="corvus-slider w-full"
              />
              <div className="mt-1 flex justify-between text-[12px] text-fg-muted">
                <span className={uiScale === "compact" ? "text-accent-bright" : ""}>Compact</span>
                <span className={uiScale === "default" ? "text-accent-bright" : ""}>Default</span>
                <span className={uiScale === "large" ? "text-accent-bright" : ""}>Large</span>
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-body-sm text-fg-muted">Typography</label>
            <Select
              value={useCorvus((s) => s.fontFamily)}
              onChange={(next) => useCorvus.getState().setFontFamily(next as any)}
              options={[
                { value: "system", label: "System Default" },
                { value: "monospace", label: "Monospace" },
                { value: "serif", label: "Serif" },
                { value: "comic", label: "Comic" },
              ]}
            />
          </div>

          <div>
            <label className="mb-1 block text-body-sm text-fg-muted">Interface Roundness</label>
            <Select
              value={useCorvus((s) => s.uiRoundness)}
              onChange={(next) => useCorvus.getState().setUiRoundness(next as any)}
              options={[
                { value: "sharp", label: "Sharp" },
                { value: "default", label: "Default" },
                { value: "rounded", label: "Rounded" },
                { value: "pill", label: "Pill" },
              ]}
            />
          </div>

          <div>
            <label className="mb-1 block text-body-sm text-fg-muted">App Opacity</label>
            <Select
              value={useCorvus((s) => s.appOpacity)}
              onChange={(next) => useCorvus.getState().setAppOpacity(next as any)}
              options={[
                { value: "solid", label: "Solid" },
                { value: "glassy", label: "Glassy" },
                { value: "transparent", label: "Transparent" },
              ]}
            />
          </div>

          <div>
            <label className="mb-1 block text-body-sm text-fg-muted">Animation Speed</label>
            <Select
              value={useCorvus((s) => s.animationSpeed)}
              onChange={(next) => useCorvus.getState().setAnimationSpeed(next as any)}
              options={[
                { value: "fast", label: "Fast" },
                { value: "default", label: "Default" },
                { value: "slow", label: "Slow" },
              ]}
            />
          </div>
        </div>
      </div>
      {import.meta.env.DEV && (
        <div className="mt-8">
          <h3 className="mb-3 text-body font-medium text-fg-muted">Orb states (dev preview)</h3>
          <div className="mb-3 flex gap-2">
            {ORB_STATES.map((s) => (
              <button
                key={s}
                onClick={() => setOrbPreview(s)}
                className={`rounded px-3 py-1.5 text-body-sm transition-colors duration-fast ${
                  orbPreview === s ? "bg-accent/30 text-fg" : "bg-white/5 text-fg-muted hover:text-fg"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="flex justify-center">
            <Orb state={orbPreview} size={140} />
          </div>
        </div>
      )}
    </div>
  );
}

function AboutPage() {
  return (
    <>
      <h2 className="mb-6 text-h3 tracking-tight font-medium">About &amp; Updates</h2>
      <AboutSettings />
    </>
  );
}

function ProvidersPage() {
  return (
    <>
      <h2 className="mb-2 text-h3 tracking-tight font-medium">AI Provider &amp; Model</h2>
      <p className="mb-6 text-body text-fg-muted">
        Switch between local Ollama and cloud providers. Keys are stored encrypted on this machine.
      </p>
      <ProviderSettings />
    </>
  );
}

function ModelsPage() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  return (
    <>
      <h2 className="mb-2 text-h3 tracking-tight font-medium">Offline Models</h2>
      <p className="mb-6 text-body text-fg-muted">
        Download more local models right here — each is annotated with how well it fits this device.
        Downloads are one-time and everything runs on your PC.
      </p>
      {backendOnline ? (
        <OllamaModels />
      ) : (
        <p className="text-body-sm text-danger">Corvus core is offline.</p>
      )}
    </>
  );
}

function DocumentsPage() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  return (
    <>
      <h2 className="mb-6 text-h3 tracking-tight font-medium">Documents Index</h2>
      {backendOnline ? (
        <DocumentsIndex />
      ) : (
        <p className="text-body-sm text-danger">Corvus core is offline.</p>
      )}
    </>
  );
}

function WakeWordPage() {
  const voice = useCorvus((s) => s.voice);
  const setWakeEnabled = useCorvus((s) => s.setWakeEnabled);
  return (
    <>
      <h2 className="mb-2 text-h3 tracking-tight font-medium">Wake Word</h2>
      <p className="mb-6 text-body text-fg-muted">
        Wake word runs locally (Whisper tiny). Say &ldquo;Hey Corvus&rdquo; to summon voice mode hands-free.
      </p>
      <Switch
        checked={voice.wakeEnabled}
        disabled={!voice.connected}
        onChange={(_e, data) => setWakeEnabled(data.checked)}
        label={`Always listening for "Hey Corvus": ${voice.wakeEnabled ? "on" : "off"}`}
      />
    </>
  );
}

function TtsVoicePage() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [ttsVoice, setTtsVoice] = useState(TTS_VOICES[0]);

  useEffect(() => {
    if (!backendOnline) return;
    void (async () => {
      const settings = await api.getSettings();
      if (settings.tts_voice) setTtsVoice(settings.tts_voice);
    })();
  }, [backendOnline]);

  async function changeTtsVoice(next: string) {
    setTtsVoice(next);
    await api.updateSettings({ tts_voice: next });
  }

  return (
    <>
      <h2 className="mb-2 text-h3 tracking-tight font-medium">TTS Voice</h2>
      <p className="mb-6 text-body text-fg-muted">
        Speech uses Microsoft neural voices online, with a Windows offline fallback.
      </p>
      <label className="mb-1 block text-body-sm text-fg-muted">Voice</label>
      <Select
        className="w-72"
        ariaLabel="Assistant voice"
        value={ttsVoice}
        disabled={!backendOnline}
        onChange={(next) => void changeTtsVoice(next)}
        options={TTS_VOICES.map((v) => ({ value: v }))}
      />
    </>
  );
}

function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [view, setView] = useState<"list" | "graph">("list");
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setMemories(await api.listMemories()), []);

  useEffect(() => {
    if (backendOnline) void refresh();
  }, [backendOnline, refresh]);

  async function remove(id: number) {
    await api.deleteMemory(id);
    await refresh();
  }

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-h3 tracking-tight font-medium">Memory</h2>
        <span className="flex items-center gap-2">
          <span className="flex overflow-hidden rounded border border-white/10">
            {(["list", "graph"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 text-body-sm capitalize transition-colors duration-fast ${
                  view === v ? "bg-accent/20 text-accent-bright" : "text-fg-muted hover:bg-white/5"
                }`}
              >
                {v}
              </button>
            ))}
          </span>
          <a
            href={api.exportMemoriesUrl()}
            download="corvus-memories.json"
            className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
          >
            Export JSON
          </a>
        </span>
      </div>
      <p className="mb-3 text-body-sm text-fg-muted">
        Everything Corvus remembers is listed here — nothing is stored silently. Delete anything you
        don&rsquo;t want kept.
      </p>
      {view === "graph" && memories.length > 0 ? (
        <MemoryGraph memories={memories} onDelete={(id) => void remove(id)} />
      ) : memories.length === 0 ? (
        <p className="text-body text-fg-muted">
          Corvus hasn&rsquo;t stored any memories yet. Durable facts from your chats (preferences,
          projects, people, favorite apps) will appear here.
        </p>
      ) : (
        <ul className="space-y-2">
          {memories.map((m) => (
            <li key={m.id} className="glass flex items-start justify-between rounded p-3">
              <div className="min-w-0 flex-1">
                <span className="mr-2 rounded-sm bg-accent/20 px-1.5 py-0.5 text-caption text-accent-bright">
                  {CATEGORY_LABEL[m.category]}
                </span>
                <span className="text-body text-fg">{m.content}</span>
                <div className="mt-1 text-caption text-fg-faint">
                  {new Date(m.created_at + "Z").toLocaleString()}
                </div>
              </div>
              <button
                onClick={() => void remove(m.id)}
                aria-label="Delete this memory"
                className="ml-3 rounded px-2 py-1 text-caption text-fg-faint transition-colors duration-fast hover:bg-danger/20 hover:text-danger"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const refresh = useCallback(async () => setEntries(await api.tailLogs(300)), []);

  useEffect(() => {
    if (!backendOnline) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [backendOnline, refresh]);

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-h3 tracking-tight font-medium">Logs</h2>
        <button
          onClick={() => void refresh()}
          className="rounded bg-accent/20 px-3 py-1.5 text-body-sm text-accent-bright transition-colors duration-fast hover:bg-accent/30"
        >
          Refresh
        </button>
      </div>
      <p className="mb-3 text-body-sm text-fg-muted">
        Structured log tail; the full file is at %LOCALAPPDATA%\Corvus\logs\corvus.log.
      </p>
      <div className="glass rounded-lg p-3 font-mono text-mono">
        {entries.length === 0 ? (
          <p className="text-fg-faint">No log entries yet.</p>
        ) : (
          entries.map((e, i) => (
            <div key={i} className="whitespace-pre-wrap break-all py-0.5">
              <span className="text-fg-faint">{e.timestamp}</span>{" "}
              <span className={LEVEL_COLOR[e.level] ?? "text-fg-muted"}>[{e.level}]</span>{" "}
              <span className="text-fg">{e.event}</span>
              {Object.entries(e)
                .filter(([k]) => !["timestamp", "level", "event"].includes(k))
                .map(([k, v]) => (
                  <span key={k} className="text-fg-muted">
                    {" "}
                    {k}={JSON.stringify(v)}
                  </span>
                ))}
            </div>
          ))
        )}
      </div>
    </>
  );
}

function BackendPage() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  return (
    <>
      <h2 className="mb-6 text-h3 tracking-tight font-medium">Backend Status</h2>
      <p className="text-body">
        {backendOnline ? (
          <div className="mt-6 flex flex-col gap-1 text-[12px] text-fg-muted">
            <span className="text-success">● Corvus core online (127.0.0.1:8765)</span>
            <span>Build: Developer Preview (0.1.0-alpha)</span>
          </div>
        ) : (
          <span className="text-danger">● Corvus core offline</span>
        )}
      </p>
    </>
  );
}

function SetupPage() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  return (
    <>
      <h2 className="mb-2 text-h3 tracking-tight font-medium">First-time Setup</h2>
      <p className="mb-6 text-body text-fg-muted">
        Re-run the welcome wizard to scan this device and choose or download a local model.
      </p>
      <button
        onClick={() =>
          void api
            .updateSettings({ onboarding_complete: false })
            .then(() => window.location.reload())
        }
        disabled={!backendOnline}
        className="rounded bg-accent px-4 py-2 text-body text-white transition-colors duration-fast enabled:hover:bg-accent-bright disabled:opacity-40"
      >
        Re-run first-time setup
      </button>
    </>
  );
}

// ─── Page map ────────────────────────────────────────────────────────

const PAGES: Record<SettingsPage, () => JSX.Element> = {
  appearance: AppearancePage,
  about: AboutPage,
  providers: ProvidersPage,
  models: ModelsPage,
  documents: DocumentsPage,
  wakework: WakeWordPage,
  ttsvoice: TtsVoicePage,
  memory: MemoryPage,
  logs: LogsPage,
  backend: BackendPage,
  setup: SetupPage,
};

// ─── Main Settings View ─────────────────────────────────────────────

export function SettingsView() {
  const [activePage, setActivePage] = useState<SettingsPage>("appearance");
  const [searchQuery, setSearchQuery] = useState("");
  const PageComponent = PAGES[activePage];

  // Filter nav items by search
  const filteredNav = SETTINGS_NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) =>
      item.label.toLowerCase().includes(searchQuery.toLowerCase())
    ),
  })).filter((group) => group.items.length > 0);

  return (
    <SectionShell title="Settings" fullWidth>
    <div className="flex h-full gap-0 overflow-hidden">
      {/* Settings Sidebar */}
      <nav className="flex h-full w-52 flex-shrink-0 flex-col border-r border-white/5 pr-4 overflow-y-auto" aria-label="Settings navigation">
        {/* Search */}
        <div className="relative mb-4">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-faint" />
          <input
            type="text"
            placeholder="Search settings..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded bg-white/5 py-1.5 pl-8 pr-3 text-body-sm text-fg placeholder:text-fg-faint border-none outline-none focus:bg-white/10 transition-colors"
          />
        </div>

        {/* Nav groups */}
        {filteredNav.map((group) => (
          <div key={group.label} className="mb-4">
            <div className="mb-1 px-2 text-caption font-semibold tracking-wider text-fg-faint uppercase">
              {group.label}
            </div>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.key}>
                  <button
                    onClick={() => setActivePage(item.key)}
                    className={`relative flex w-full items-center gap-2.5 rounded px-2.5 py-1.5 text-left text-body-sm transition-colors duration-fast ${
                      activePage === item.key
                        ? "bg-white/10 text-fg font-medium"
                        : "text-fg-muted hover:bg-white/5 hover:text-fg"
                    }`}
                  >
                    <span aria-hidden className="flex-shrink-0">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto pt-2 pb-8 flex justify-center">
        <div className="w-full max-w-4xl py-2 px-8">
          <PageComponent />
        </div>
      </div>
    </div>
    </SectionShell>
  );
}
