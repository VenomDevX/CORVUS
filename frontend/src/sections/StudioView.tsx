import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  History,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Square,
  Trash2,
  Volume2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Search,
  MoreVertical,
  ThumbsUp,
  ThumbsDown,
  Share2,
  Type,
  ListFilter
} from "lucide-react";
import { SectionShell } from "./SectionShell";
import {
  api,
  type EdgeVoice,
  type PiperVoice,
  type StudioVoices,
  type VoiceEngine,
  type Voiceover,
} from "../lib/api";
import { useCorvus } from "../state/store";

const MAX_CHARS = 20_000;

function localeLabel(locale: string): string {
  try {
    const [lang, region] = locale.split("-");
    const langName = new Intl.DisplayNames(["en"], { type: "language" }).of(lang) ?? lang;
    return region ? `${langName} (${region})` : langName;
  } catch {
    return locale;
  }
}

function fmtTime(seconds: number): string {
  if (!isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function languageOf(locale: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(locale.split(/[-_]/)[0]) ?? locale;
  } catch {
    return locale;
  }
}

function regionOf(locale: string): string {
  return locale.split(/[-_]/)[1] ?? "";
}

function regionLabel(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

const AVATAR_GRADIENTS = [
  "from-teal-300 to-cyan-600",
  "from-sky-300 to-blue-600",
  "from-violet-300 to-purple-600",
  "from-rose-300 to-pink-600",
  "from-amber-200 to-orange-500",
  "from-emerald-300 to-green-600",
  "from-fuchsia-300 to-violet-600",
  "from-indigo-300 to-blue-700",
];

/** Deterministic gradient avatar with initials — one look per voice name. */
function VoiceAvatar({ name, className = "h-10 w-10 text-sm" }: { name: string; className?: string }) {
  const hash = [...name].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) >>> 0;
  const grad = AVATAR_GRADIENTS[hash % AVATAR_GRADIENTS.length];
  const parts = name.split(/[\s\-_]+/).filter(Boolean);
  const initials = (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 1)).toUpperCase();
  return (
    <div
      className={`relative flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br ${grad} font-bold text-white shadow-md ring-1 ring-white/20 ${className}`}
    >
      <div className="absolute -left-1 -top-1 h-2/3 w-2/3 rounded-full bg-white/30 blur-[6px]" />
      <span className="relative drop-shadow-sm">{initials}</span>
    </div>
  );
}

function FilterChip({
  label,
  value,
  selected,
  options,
  onSelect,
  onClear,
}: {
  label: string;
  value: string;
  selected: string;
  options: { value: string; label: string }[];
  onSelect: (v: string) => void;
  onClear?: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={
          value
            ? "flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-black shadow-sm"
            : "flex items-center gap-1.5 rounded-full border border-white/10 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-gray-300 shadow-sm transition-colors hover:bg-zinc-700/70"
        }
      >
        {value && onClear ? (
          <span
            onClick={(e) => {
              e.stopPropagation();
              onClear();
              setOpen(false);
            }}
            className="-mt-0.5 text-lg leading-none text-gray-500 hover:text-black"
          >
            ×
          </span>
        ) : !value ? (
          <span className="-mt-0.5 text-lg leading-none text-gray-500">+</span>
        ) : null}
        {value ? (
          <>
            <span className="font-medium text-gray-600">{label}</span> {value}
          </>
        ) : (
          label
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full z-50 mt-1.5 max-h-64 w-56 overflow-y-auto rounded-xl border border-white/10 bg-zinc-900 p-1.5 shadow-2xl">
            {options.map((o) => (
              <button
                key={o.value}
                onClick={() => {
                  onSelect(o.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                  selected === o.value ? "bg-white/10 font-medium text-white" : "text-gray-300 hover:bg-white/5"
                }`}
              >
                {o.label}
                {selected === o.value && <span className="text-xs">✓</span>}
              </button>
            ))}
            {options.length === 0 && <div className="px-2.5 py-2 text-xs text-gray-500">No options</div>}
          </div>
        </>
      )}
    </div>
  );
}

function GlobalPlayer({ item, autoplay }: { item?: Voiceover; autoplay?: boolean }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    setPlaying(false);
    setProgress(0);
  }, [item?.id]);

  if (!item) {
    return (
      <div className="flex h-24 items-center justify-center gap-4 border-t border-white/10 bg-black px-6 py-2 text-gray-500">
        <Volume2 className="h-5 w-5 opacity-50" />
        <span className="text-sm">No audio selected</span>
      </div>
    );
  }

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) audio.pause();
    else void audio.play();
  };

  const seek = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + seconds));
  };

  return (
    <div className="flex h-24 items-center justify-between border-t border-white/10 bg-black px-6 shadow-sm">
      {/* Left section: Info */}
      <div className="flex items-center gap-4 w-1/4 min-w-0">
        <VoiceAvatar name={item.voice} />
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-white">{item.voice}</span>
            <span className="truncate text-xs text-gray-500">· Created recently</span>
          </div>
        </div>
      </div>

      {/* Middle section: Controls & Timeline */}
      <div className="flex flex-1 flex-col items-center justify-center max-w-2xl px-8">
        <div className="flex items-center gap-6 mb-1">
          <button onClick={() => seek(-10)} className="text-gray-400 hover:text-white transition-colors" aria-label="Rewind 10 seconds">
            <RotateCcw className="h-5 w-5" />
          </button>
          <button
            onClick={toggle}
            aria-label={playing ? "Pause" : "Play"}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-black transition-transform hover:scale-105 active:scale-95 shadow-md"
          >
            {playing ? <Pause className="h-5 w-5 fill-current" /> : <Play className="h-5 w-5 fill-current ml-0.5" />}
          </button>
          <button onClick={() => seek(10)} className="text-gray-400 hover:text-white transition-colors" aria-label="Forward 10 seconds">
            <RotateCw className="h-5 w-5" />
          </button>
        </div>
        <div className="flex w-full items-center gap-3">
          <span className="w-10 text-right text-xs text-gray-500 font-mono">
            {fmtTime(progress)}
          </span>
          <input
            type="range"
            min={0}
            max={duration || 1}
            step={0.1}
            value={progress}
            onChange={(e) => {
              const t = Number(e.target.value);
              if (audioRef.current) audioRef.current.currentTime = t;
              setProgress(t);
            }}
            aria-label="Seek"
            className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-[#161B22] accent-white transition-all hover:bg-white/10"
          />
          <span className="w-10 text-xs text-gray-500 font-mono">
            {fmtTime(duration)}
          </span>
        </div>
      </div>

      {/* Right section: Actions */}
      <div className="flex items-center gap-3 w-1/4 justify-end">
        <div className="flex items-center border border-white/10 rounded-md p-1 mr-2 bg-[#161B22]">
          <button className="rounded p-1.5 text-gray-400 hover:bg-white/10 hover:text-white transition-colors">
            <ThumbsUp className="h-4 w-4" />
          </button>
          <div className="w-px h-4 bg-white/10 mx-1" />
          <button className="rounded p-1.5 text-gray-400 hover:bg-white/10 hover:text-white transition-colors">
            <ThumbsDown className="h-4 w-4" />
          </button>
        </div>
        <button className="flex items-center gap-1.5 rounded-md border border-white/10 bg-[#161B22] px-3 py-1.5 text-sm font-medium text-gray-300 hover:bg-white/5 transition-colors">
          <Share2 className="h-4 w-4" />
          Share
        </button>
        <a
          href={api.voiceoverAudioUrl(item.id)}
          download={item.filename}
          aria-label="Download audio"
          className="flex items-center justify-center rounded-md border border-white/10 bg-[#161B22] p-2 text-gray-300 hover:bg-white/5 transition-colors"
        >
          <Download className="h-4 w-4" />
        </a>
        <button className="rounded-md p-2 text-gray-400 hover:bg-white/10 transition-colors">
          <ChevronDown className="h-5 w-5" />
        </button>
      </div>

      <audio
        ref={audioRef}
        src={api.voiceoverAudioUrl(item.id)}
        preload="metadata"
        autoPlay={autoplay}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setProgress(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
      />
    </div>
  );
}

function HistoryCard({
  item,
  active,
  onClick,
  onDelete,
  onReuse,
}: {
  item: Voiceover;
  active: boolean;
  onClick: () => void;
  onDelete: () => void;
  onReuse: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`group relative cursor-pointer border-b border-white/5 px-6 py-4 transition-all hover:bg-white/5 ${
        active ? "bg-white/10" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm leading-relaxed text-gray-200" title={item.text}>
            {item.text}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-white">{item.voice}</span>
            <span className="text-xs text-gray-500">·</span>
            <span className="text-xs text-gray-400">
              {new Date(`${item.created_at}Z`).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onReuse();
            }}
            className="rounded p-1.5 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
            title="Reuse settings"
          >
            <History className="h-4 w-4" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="rounded p-1.5 text-red-400 transition-colors hover:bg-red-500/20 hover:text-red-300"
            title="Delete"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function StudioView() {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [voices, setVoices] = useState<StudioVoices>({ edge: [], piper: [] });
  const [items, setItems] = useState<Voiceover[]>([]);
  const [engine, setEngine] = useState<VoiceEngine>("edge");
  const [voice, setVoice] = useState("");
  const [search, setSearch] = useState("");
  const [gender, setGender] = useState<"" | "Male" | "Female">("");
  const [lang, setLang] = useState("English");
  const [accent, setAccent] = useState("");
  const [autoplay, setAutoplay] = useState(true);
  const [isModelOpen, setIsModelOpen] = useState(false);
  const [sortOrder, setSortOrder] = useState<"A-Z" | "Z-A" | "Locale">("A-Z");
  const [isSortOpen, setIsSortOpen] = useState(false);
  const [text, setText] = useState("");
  const [rate, setRate] = useState(0);
  const [pitch, setPitch] = useState(0);
  const [volume, setVolume] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [previewing, setPreviewing] = useState<string | false>(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewRef = useRef<HTMLAudioElement | null>(null);

  const [sidebarTab, setSidebarTab] = useState<"settings" | "history">("settings");
  const [activeVoiceoverId, setActiveVoiceoverId] = useState<number | null>(null);
  const [isVoicePickerOpen, setIsVoicePickerOpen] = useState(false);

  const refresh = useCallback(async () => {
    const [v, list] = await Promise.all([api.studioVoices(), api.listVoiceovers()]);
    setVoices(v);
    setItems(list);
  }, []);

  useEffect(() => {
    if (backendOnline) void refresh().catch(() => undefined);
  }, [backendOnline, refresh]);

  const edgeFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = voices.edge.filter(
      (v) =>
        (!gender || v.gender === gender) &&
        (!lang || languageOf(v.locale) === lang) &&
        (!accent || regionOf(v.locale) === accent) &&
        (!q || v.id.toLowerCase().includes(q) || localeLabel(v.locale).toLowerCase().includes(q)),
    );
    return filtered.sort((a, b) => {
      if (sortOrder === "A-Z") return a.name.localeCompare(b.name);
      if (sortOrder === "Z-A") return b.name.localeCompare(a.name);
      return localeLabel(a.locale).localeCompare(localeLabel(b.locale));
    });
  }, [voices.edge, search, gender, lang, accent, sortOrder]);

  const piperFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = voices.piper.filter(
      (v) =>
        (!gender || v.gender === gender) &&
        (!lang || languageOf(v.language).toLowerCase().includes(lang.toLowerCase())) &&
        (!q || v.name.toLowerCase().includes(q) || v.language.toLowerCase().includes(q)),
    );
    return filtered.sort((a, b) => {
      if (sortOrder === "A-Z") return a.name.localeCompare(b.name);
      if (sortOrder === "Z-A") return b.name.localeCompare(a.name);
      return a.language.localeCompare(b.language);
    });
  }, [voices.piper, search, gender, lang, sortOrder]);

  const languageOptions = useMemo(() => {
    const source =
      engine === "edge"
        ? voices.edge.map((v) => languageOf(v.locale))
        : voices.piper.map((v) => languageOf(v.language));
    return [...new Set(source)].sort().map((l) => ({ value: l, label: l }));
  }, [voices, engine]);

  const accentOptions = useMemo(() => {
    if (engine !== "edge") return [];
    const regions = voices.edge
      .filter((v) => !lang || languageOf(v.locale) === lang)
      .map((v) => regionOf(v.locale))
      .filter(Boolean);
    return [...new Set(regions)].sort().map((r) => ({ value: r, label: `${regionLabel(r)} (${r})` }));
  }, [voices.edge, engine, lang]);

  const edgeGroups = useMemo(() => {
    const groups = new Map<string, EdgeVoice[]>();
    for (const v of edgeFiltered) {
      const key = localeLabel(v.locale);
      groups.set(key, [...(groups.get(key) ?? []), v]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [edgeFiltered]);

  useEffect(() => {
    if (engine === "edge") {
      if (!voices.edge.some((v) => v.id === voice)) {
        setVoice(voices.edge.find((v) => v.id === "en-US-AriaNeural")?.id ?? voices.edge[0]?.id ?? "");
      }
    } else if (!voices.piper.some((v) => v.id === voice && v.installed)) {
      setVoice(voices.piper.find((v) => v.installed)?.id ?? "");
    }
  }, [engine, voices, voice]);

  const selectedPiper: PiperVoice | undefined = voices.piper.find((v) => v.id === voice);
  const selectedVoice = engine === "edge" ? voices.edge.find((v) => v.id === voice) : selectedPiper;
  const canGenerate =
    backendOnline &&
    !generating &&
    text.trim().length > 0 &&
    text.length <= MAX_CHARS &&
    voice !== "" &&
    (engine === "edge" || selectedPiper?.installed === true);

  async function generate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError(null);
    try {
      const row = await api.generateVoiceover({
        text: text.trim(),
        engine,
        voice,
        rate,
        pitch,
        volume,
      });
      setItems((prev) => [row, ...prev]);
      setActiveVoiceoverId(row.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function preview(targetEngine: VoiceEngine, targetVoice: string) {
    if (!targetVoice || previewing === targetVoice) return;
    setPreviewing(targetVoice);
    setError(null);
    try {
      const blob = await api.previewVoice(targetEngine, targetVoice);
      previewRef.current?.pause();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      previewRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPreviewing(false);
      };
      audio.onpause = () => {
        setPreviewing(false);
      };
      await audio.play();
    } catch (e) {
      setError(e instanceof Error ? e.message : "preview failed");
      setPreviewing(false);
    }
  }

  async function downloadPiper(id: string) {
    setDownloading(id);
    setError(null);
    try {
      await api.downloadPiperVoice(id);
      await refresh();
      setVoice(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "voice download failed");
    } finally {
      setDownloading(null);
    }
  }

  const activeVoiceover = items.find((i) => i.id === activeVoiceoverId);

  return (
    <SectionShell title="Voice Studio">
      <div className="flex h-full min-h-0 flex-col lg:flex-row">
        {/* Main Content Area (Left) */}
        <div className="flex flex-1 min-h-0 flex-col">
          {/* Top Bar for Tabs if needed, currently empty or for future Speech/Image/Video tabs */}
          <div className="flex items-center gap-6 border-b border-white/5 px-6 py-4">
            <button className="text-body-sm font-medium text-white border-b-2 border-white pb-1">
              Speech
            </button>
            <button className="text-body-sm font-medium text-fg-muted hover:text-fg pb-1">
              Image
            </button>
            <button className="text-body-sm font-medium text-fg-muted hover:text-fg pb-1">
              Video
            </button>
            <button className="text-body-sm font-medium text-fg-muted hover:text-fg pb-1">
              Sound Effects
            </button>
          </div>

          <div className="flex-1 min-h-0 flex flex-col p-6 lg:p-10">
            <div className="flex-1 min-h-0 flex flex-col">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
                placeholder="Type or paste the script for your voiceover…"
                className="flex-1 resize-none bg-transparent p-0 text-xl font-light leading-relaxed text-fg outline-none placeholder:text-fg-muted/50"
              />
              <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-4 text-xs font-medium uppercase tracking-wider text-fg-faint">
                <span>
                  {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters
                </span>
                {error && <span className="text-danger normal-case">{error}</span>}
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => void generate()}
                disabled={!canGenerate}
                className="flex items-center justify-center gap-2 rounded-xl bg-white px-8 py-3 text-body font-semibold text-black shadow-lg shadow-white/10 transition-all duration-fast hover:bg-white/90 hover:shadow-white/20 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
              >
                {generating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Volume2 className="h-5 w-5" />}
                {generating ? "Synthesizing…" : "Generate"}
              </button>
            </div>
          </div>

          {/* Global Player Bar */}
          {activeVoiceover && <GlobalPlayer item={activeVoiceover} autoplay={autoplay} />}
        </div>

        {/* Right Sidebar */}
        <div className="flex w-full min-h-0 flex-col border-t border-white/10 bg-black lg:w-[420px] lg:border-l lg:border-t-0 xl:w-[460px]">
          {isVoicePickerOpen ? (
            <div className="flex flex-col h-full text-white bg-black">
              <div className="flex items-center gap-3 p-4 py-3">
                <button 
                  onClick={() => setIsVoicePickerOpen(false)} 
                  className="rounded-md border border-white/10 p-1.5 text-gray-300 hover:bg-white/5 transition-colors shadow-sm"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <span className="text-lg font-medium tracking-tight">Select a voice</span>
              </div>
              
              <div className="flex items-center gap-8 px-6 mt-1">
                <button className="flex items-center gap-2 py-3 text-sm font-semibold border-b-2 border-white text-white">
                  <Type className="h-4 w-4" /> Explore
                </button>
                <button className="flex items-center gap-2 py-3 text-sm font-medium border-b-2 border-transparent text-gray-400 hover:text-white">
                  My Voices
                </button>
              </div>

              <div className="p-4 flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <div className="flex-1 flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 bg-[#161B22] focus-within:border-white/30 focus-within:ring-2 focus-within:ring-white/10 transition-all">
                    <Search className="h-4 w-4 text-gray-400" />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Start typing to search..."
                      className="flex-1 bg-transparent text-sm font-medium outline-none text-white placeholder:text-gray-500 placeholder:font-normal"
                    />
                  </div>
                  <button 
                    onClick={() => setIsSortOpen(!isSortOpen)}
                    className="rounded-lg border border-white/10 p-2 text-gray-300 hover:bg-white/5 shadow-sm transition-colors"
                  >
                    <ListFilter className="h-4 w-4" />
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <FilterChip
                    label="Language"
                    value={lang}
                    selected={lang}
                    options={languageOptions}
                    onSelect={(v) => {
                      setLang(v);
                      setAccent("");
                    }}
                    onClear={() => {
                      setLang("");
                      setAccent("");
                    }}
                  />
                  {engine === "edge" && (
                    <FilterChip
                      label="Accent"
                      value={accent ? regionLabel(accent) : ""}
                      selected={accent}
                      options={accentOptions}
                      onSelect={setAccent}
                      onClear={() => setAccent("")}
                    />
                  )}
                  <FilterChip
                    label="Category"
                    value={engine === "edge" ? "Online" : "Offline"}
                    selected={engine}
                    options={[
                      { value: "edge", label: "Online · Neural" },
                      { value: "piper", label: "Offline · Local" },
                    ]}
                    onSelect={(v) => setEngine(v as VoiceEngine)}
                  />
                  <FilterChip
                    label="Gender"
                    value={gender}
                    selected={gender}
                    options={[
                      { value: "Female", label: "Female" },
                      { value: "Male", label: "Male" },
                    ]}
                    onSelect={(v) => setGender(v as "Male" | "Female")}
                    onClear={() => setGender("")}
                  />

                  <div className="relative ml-auto">
                    {isSortOpen && (
                      <>
                        <div className="fixed inset-0 z-40" onClick={() => setIsSortOpen(false)} />
                        <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-xl border border-white/10 bg-[#161B22] p-2 shadow-xl flex flex-col gap-3">
                          <div>
                            <div className="mb-1.5 px-2 text-[10px] font-bold uppercase tracking-wider text-gray-500">Sort</div>
                            {(["A-Z", "Z-A", "Locale"] as const).map((opt) => (
                              <button
                                key={opt}
                                onClick={() => setSortOrder(opt)}
                                className={`flex w-full items-center rounded-md px-2 py-1.5 text-sm transition-colors ${sortOrder === opt ? "bg-white/10 text-white font-medium" : "text-gray-400 hover:bg-white/5"}`}
                              >
                                {opt === "Locale" ? "Region" : opt}
                              </button>
                            ))}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-4 pb-10">
                {engine === "edge" ? (
                  voices.edge.length === 0 ? (
                    <div className="flex h-full items-center justify-center p-4 text-center text-sm text-gray-400">
                      Neural voice catalog unavailable.<br />
                      Check connection or use offline voices.
                    </div>
                  ) : (
                    edgeGroups.map(([group, groupVoices]) => (
                      <div key={group} className="mb-2 last:mb-0">
                        <div className="sticky top-0 z-10 bg-black/95 px-2 py-2 text-[10px] font-bold uppercase tracking-wider text-gray-500 backdrop-blur-md">
                          {group}
                        </div>
                        <div className="space-y-1">
                          {groupVoices.map((v) => (
                            <div
                              key={v.id}
                              className={`group relative flex w-full items-center gap-3 rounded-lg p-2 transition-all duration-fast ${
                                voice === v.id
                                  ? "bg-white/10"
                                  : "hover:bg-white/5"
                              }`}
                            >
                              <button
                                onClick={() => setVoice(v.id)}
                                aria-pressed={voice === v.id}
                                className="absolute inset-0 z-0 rounded-lg"
                                aria-label={`Select ${v.name}`}
                              />
                              <div className="relative z-10 shrink-0">
                                <VoiceAvatar name={v.name} />
                                {voice === v.id && (
                                  <div className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-white text-black border-2 border-black shadow-sm">
                                    <span className="text-[10px]">✓</span>
                                  </div>
                                )}
                              </div>
                              <div className="relative z-10 flex min-w-0 flex-1 flex-col pr-2">
                                <span className={`truncate text-sm font-semibold tracking-tight ${voice === v.id ? 'text-white' : 'text-gray-300 group-hover:text-white'}`}>
                                  {v.name}
                                </span>
                                <span className="truncate text-[13px] text-gray-500 font-medium">
                                  {v.gender}
                                </span>
                              </div>
                              <div className="relative z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (previewing === v.id) {
                                      previewRef.current?.pause();
                                      setPreviewing(false);
                                    } else {
                                      void preview("edge", v.id);
                                    }
                                  }}
                                  className="shrink-0 rounded p-1.5 hover:bg-white/20 transition-colors text-white"
                                  title="Preview Voice"
                                >
                                  {previewing === v.id ? <Square className="h-4 w-4 fill-current" /> : <Play className="h-4 w-4 fill-current ml-0.5" />}
                                </button>
                                <button className="shrink-0 rounded p-1.5 text-gray-400 hover:bg-white/20 transition-colors">
                                  <MoreVertical className="h-4 w-4" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))
                  )
                ) : (
                  <div className="space-y-1">
                    {piperFiltered.map((v) => (
                      <div
                        key={v.id}
                        className={`group relative flex w-full items-center gap-3 rounded-lg p-2 transition-all duration-fast ${
                          voice === v.id
                            ? "bg-white/10"
                            : "hover:bg-white/5"
                        } ${!v.installed ? "opacity-75 grayscale-[0.5]" : ""}`}
                      >
                        <button
                          onClick={() => v.installed && setVoice(v.id)}
                          disabled={!v.installed}
                          className="absolute inset-0 z-0 rounded-lg disabled:cursor-default"
                          aria-label={`Select ${v.name}`}
                        />
                        <div className="relative z-10 shrink-0">
                          <VoiceAvatar name={v.name} />
                          {voice === v.id && (
                            <div className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-white text-black border-2 border-black shadow-sm">
                              <span className="text-[10px]">✓</span>
                            </div>
                          )}
                        </div>
                        <div className="relative z-10 flex min-w-0 flex-1 flex-col pr-2">
                          <span className={`truncate text-sm font-semibold tracking-tight ${voice === v.id ? 'text-white' : 'text-gray-300 group-hover:text-white'}`}>
                            {v.name}
                          </span>
                          <span className="truncate text-[13px] text-gray-500 font-medium">
                            {v.gender} · {v.language}
                          </span>
                        </div>
                        {v.installed ? (
                          <div className="relative z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                if (previewing === v.id) {
                                  previewRef.current?.pause();
                                  setPreviewing(false);
                                } else {
                                  void preview("piper", v.id);
                                }
                              }}
                              className="shrink-0 rounded p-1.5 hover:bg-white/20 transition-colors text-white"
                              title="Preview Voice"
                            >
                              {previewing === v.id ? <Square className="h-4 w-4 fill-current" /> : <Play className="h-4 w-4 fill-current ml-0.5" />}
                            </button>
                            <button className="shrink-0 rounded p-1.5 text-gray-400 hover:bg-white/20 transition-colors">
                              <MoreVertical className="h-4 w-4" />
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void downloadPiper(v.id);
                            }}
                            disabled={downloading !== null}
                            className="relative z-10 flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-[#161B22] px-2.5 py-1.5 text-xs font-semibold text-gray-300 transition-colors hover:bg-white/5 disabled:opacity-50 shadow-sm"
                          >
                            {downloading === v.id ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Download className="h-3.5 w-3.5" />
                            )}
                            {v.size_mb} MB
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col bg-black text-white">
              <div className="flex items-center gap-8 px-6 mt-4 border-b border-white/10">
                <button
                  onClick={() => setSidebarTab("settings")}
                  className={`flex items-center gap-2 py-3 text-[13px] font-semibold transition-colors ${
                    sidebarTab === "settings"
                      ? "border-b-2 border-white text-white"
                      : "border-b-2 border-transparent text-gray-500 hover:text-white"
                  }`}
                >
                  Settings
                </button>
                <button
                  onClick={() => setSidebarTab("history")}
                  className={`flex items-center gap-2 py-3 text-[13px] font-semibold transition-colors ${
                    sidebarTab === "history"
                      ? "border-b-2 border-white text-white"
                      : "border-b-2 border-transparent text-gray-500 hover:text-white"
                  }`}
                >
                  History
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6">
                {sidebarTab === "settings" ? (
                  <div className="flex flex-col gap-6">
                    <div className="space-y-2">
                      <label className="text-sm font-semibold tracking-tight text-white">Voice</label>
                      <button
                        onClick={() => setIsVoicePickerOpen(true)}
                        className="flex w-full items-center justify-between rounded-xl border border-white/10 p-3 bg-zinc-800 hover:bg-zinc-700/70 transition-all shadow-sm focus:ring-2 focus:ring-white/10 outline-none"
                      >
                        <div className="flex items-center gap-3">
                          <VoiceAvatar name={selectedVoice?.name || "A"} className="h-6 w-6 text-[10px]" />
                          <span className="text-[13px] font-semibold text-white">
                            {selectedVoice?.name || "Select Voice"}
                            {selectedVoice?.gender ? ` - ${selectedVoice.gender}` : ""}
                          </span>
                        </div>
                        <ChevronRight className="h-4 w-4 text-gray-500" />
                      </button>
                    </div>
                    
                    <div className="space-y-2">
                      <label className="text-sm font-semibold tracking-tight text-white">Model</label>
                      <div className="relative">
                        <button
                          onClick={() => setIsModelOpen((o) => !o)}
                          className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-zinc-800 p-3 text-[13px] font-semibold text-white shadow-sm transition-all hover:bg-zinc-700/70 focus:ring-2 focus:ring-white/10 outline-none"
                        >
                          {engine === "edge"
                            ? "Multilingual v1 (Online)"
                            : "Multilingual v2 (Offline)"}
                          <ChevronDown
                            className={`h-4 w-4 text-gray-500 transition-transform duration-fast ${isModelOpen ? "rotate-180" : ""}`}
                          />
                        </button>
                        {isModelOpen && (
                          <>
                            <div className="fixed inset-0 z-40" onClick={() => setIsModelOpen(false)} />
                            <div className="absolute left-0 right-0 top-full z-50 mt-2 rounded-xl border border-white/10 bg-zinc-900 p-1.5 shadow-2xl">
                              {(
                                [
                                  {
                                    value: "edge",
                                    title: "Multilingual v1",
                                    sub: "Online · Full neural catalog, needs internet",
                                  },
                                  {
                                    value: "piper",
                                    title: "Multilingual v2",
                                    sub: "Offline · Runs locally, downloadable voices",
                                  },
                                ] as const
                              ).map((m) => (
                                <button
                                  key={m.value}
                                  onClick={() => {
                                    setEngine(m.value);
                                    setIsModelOpen(false);
                                  }}
                                  className={`flex w-full items-start justify-between rounded-lg px-3 py-2.5 text-left transition-colors ${
                                    engine === m.value ? "bg-white/10" : "hover:bg-white/5"
                                  }`}
                                >
                                  <span className="flex flex-col">
                                    <span className="text-[13px] font-semibold text-white">{m.title}</span>
                                    <span className="text-xs text-gray-500">{m.sub}</span>
                                  </span>
                                  {engine === m.value && <span className="mt-0.5 text-xs text-white">✓</span>}
                                </button>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                    
                    <h3 className="text-sm font-semibold tracking-tight text-white mb-4 mt-6">Voice Settings</h3>
                    <div className="space-y-6 pt-2">
                      {(
                        [
                          ["Speed", rate, setRate, -50, 100, "Slower", "Faster"],
                          ["Pitch", pitch, setPitch, -50, 50, "Lower", "Higher"],
                          ["Volume", volume, setVolume, -50, 50, "Quieter", "Louder"],
                        ] as const
                      ).map(([label, value, set, min, max, minLabel, maxLabel]) => (
                        <label key={label} className="block group">
                          <div className="mb-0.5 flex justify-between items-end">
                            <span className="text-sm font-semibold tracking-tight text-white border-b border-white/20 border-dashed">{label}</span>
                            <span className="text-xs text-white/50">{value}</span>
                          </div>
                          <div className="flex justify-between text-xs text-gray-500 font-medium mb-2">
                            <span>{minLabel}</span>
                            <span>{maxLabel}</span>
                          </div>
                          <div className="relative flex items-center h-4">
                            {/* Track background */}
                            <div className="absolute w-full h-1 bg-[#161B22] rounded-full border border-white/5" />
                            {/* Filled track */}
                            <div 
                              className="absolute h-1 bg-white rounded-full" 
                              style={{ width: `${((value - min) / (max - min)) * 100}%` }}
                            />
                            {/* The input range itself, made transparent but overlaid for interaction */}
                            <input
                              type="range"
                              min={min}
                              max={max}
                              value={value}
                              onChange={(e) => set(Number(e.target.value))}
                              disabled={engine === "piper" && label !== "Speed" && label !== "Volume"}
                              className="absolute w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
                            />
                            {/* Custom thumb */}
                            <div 
                              className="absolute h-3.5 w-3.5 rounded-full bg-white shadow-md group-hover:scale-110 transition-transform pointer-events-none"
                              style={{ left: `calc(${((value - min) / (max - min)) * 100}% - 7px)` }}
                            />
                          </div>
                        </label>
                      ))}

                      <div className="flex justify-end pt-1">
                        <button
                          onClick={() => {
                            setRate(0);
                            setPitch(0);
                            setVolume(0);
                          }}
                          className="flex items-center gap-1.5 text-xs font-medium text-gray-500 transition-colors hover:text-white"
                        >
                          <RotateCcw className="h-3.5 w-3.5" /> Reset to defaults
                        </button>
                      </div>
                    </div>

                    <h3 className="text-sm font-semibold tracking-tight text-white mt-2">Playback</h3>
                    <div className="flex items-center justify-between">
                      <div className="flex flex-col">
                        <span className="text-[13px] font-medium text-gray-200">Autoplay</span>
                        <span className="text-xs text-gray-500">Play new voiceovers automatically</span>
                      </div>
                      <button
                        role="switch"
                        aria-checked={autoplay}
                        onClick={() => setAutoplay((a) => !a)}
                        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                          autoplay ? "bg-white" : "bg-zinc-700"
                        }`}
                      >
                        <span
                          className={`absolute top-0.5 h-4 w-4 rounded-full shadow-sm transition-transform ${
                            autoplay ? "translate-x-[18px] bg-black" : "translate-x-0.5 bg-gray-400"
                          }`}
                        />
                      </button>
                    </div>
                  </div>
                ) : (
              <div className="flex h-full flex-col">
                {items.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center p-8 text-center text-fg-muted">
                    <div className="mb-4 rounded-full bg-white/5 p-4">
                      <History className="h-8 w-8 opacity-50" />
                    </div>
                    <p className="text-body font-medium text-fg">No history yet</p>
                    <p className="mt-2 text-body-sm leading-relaxed">
                      Generated voiceovers will appear here.
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col">
                    {items.map((item) => (
                      <HistoryCard
                        key={item.id}
                        item={item}
                        active={activeVoiceoverId === item.id}
                        onClick={() => setActiveVoiceoverId(item.id)}
                        onDelete={() => {
                          void api.deleteVoiceover(item.id).then(() => {
                            setItems((prev) => prev.filter((v) => v.id !== item.id));
                            if (activeVoiceoverId === item.id) {
                              setActiveVoiceoverId(null);
                            }
                          });
                        }}
                        onReuse={() => {
                          setText(item.text);
                          setEngine(item.engine);
                          setVoice(item.voice);
                          setRate(item.rate);
                          setPitch(item.pitch);
                          setVolume(item.volume);
                          setSidebarTab("settings");
                        }}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
          )}
        </div>
      </div>
    </SectionShell>
  );
}

