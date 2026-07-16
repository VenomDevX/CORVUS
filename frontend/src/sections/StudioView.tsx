import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Trash2,
  Volume2,
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

/** Human label for an Edge locale, e.g. "en-US" -> "English (US)". */
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

/** One generated voiceover: player card with seek, download, delete, reuse. */
function VoiceoverCard({
  item,
  onDelete,
  onReuse,
}: {
  item: Voiceover;
  onDelete: () => void;
  onReuse: () => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) audio.pause();
    else void audio.play();
  };

  return (
    <div className="liquid-glass rounded-xl p-4">
      <div className="flex items-start gap-3">
        <button
          onClick={toggle}
          aria-label={playing ? "Pause" : "Play"}
          className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors duration-fast hover:bg-accent-bright"
        >
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 pl-0.5" />}
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-body text-fg" title={item.text}>
            {item.text}
          </p>
          <p className="mt-0.5 text-caption text-fg-faint">
            {item.voice} · {item.engine === "edge" ? "Edge neural" : "Piper (offline)"}
            {item.rate !== 0 && ` · speed ${item.rate > 0 ? "+" : ""}${item.rate}%`}
            {item.pitch !== 0 && ` · pitch ${item.pitch > 0 ? "+" : ""}${item.pitch}Hz`}
            {" · "}
            {new Date(`${item.created_at}Z`).toLocaleString()}
          </p>
          <div className="mt-2 flex items-center gap-2">
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
              className="h-1 flex-1 accent-[var(--c-accent)]"
            />
            <span className="w-20 shrink-0 text-right font-mono text-caption text-fg-faint">
              {fmtTime(progress)} / {fmtTime(duration)}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <a
            href={api.voiceoverAudioUrl(item.id)}
            download={item.filename}
            aria-label="Download audio"
            className="rounded p-2 text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg"
          >
            <Download className="h-4 w-4" />
          </a>
          <button
            onClick={onReuse}
            aria-label="Reuse text and settings"
            title="Load this text and settings back into the editor"
            className="rounded p-2 text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <button
            onClick={onDelete}
            aria-label="Delete voiceover"
            className="rounded p-2 text-fg-muted transition-colors duration-fast hover:bg-danger/20 hover:text-danger"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
      <audio
        ref={audioRef}
        src={api.voiceoverAudioUrl(item.id)}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setProgress(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
      />
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
  const [text, setText] = useState("");
  const [rate, setRate] = useState(0);
  const [pitch, setPitch] = useState(0);
  const [volume, setVolume] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewRef = useRef<HTMLAudioElement | null>(null);

  const refresh = useCallback(async () => {
    const [v, list] = await Promise.all([api.studioVoices(), api.listVoiceovers()]);
    setVoices(v);
    setItems(list);
  }, []);

  useEffect(() => {
    if (backendOnline) void refresh().catch(() => undefined);
  }, [backendOnline, refresh]);

  // Keep the selected voice valid for the active engine.
  const edgeFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return voices.edge.filter(
      (v) =>
        (!gender || v.gender === gender) &&
        (!q ||
          v.id.toLowerCase().includes(q) ||
          localeLabel(v.locale).toLowerCase().includes(q)),
    );
  }, [voices.edge, search, gender]);

  const piperFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return voices.piper.filter(
      (v) =>
        (!gender || v.gender === gender) &&
        (!q || v.name.toLowerCase().includes(q) || v.language.toLowerCase().includes(q)),
    );
  }, [voices.piper, search, gender]);

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
  const canGenerate =
    backendOnline && !generating && text.trim().length > 0 && text.length <= MAX_CHARS &&
    voice !== "" && (engine === "edge" || selectedPiper?.installed === true);

  async function generate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError(null);
    try {
      const row = await api.generateVoiceover({ text: text.trim(), engine, voice, rate, pitch, volume });
      setItems((prev) => [row, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function preview() {
    if (!voice || previewing) return;
    setPreviewing(true);
    setError(null);
    try {
      const blob = await api.previewVoice(engine, voice);
      previewRef.current?.pause();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      previewRef.current = audio;
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (e) {
      setError(e instanceof Error ? e.message : "preview failed");
    } finally {
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

  return (
    <SectionShell title="Voice Studio">
      <div className="grid h-full min-h-0 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Composer */}
        <div className="liquid-glass flex min-h-0 flex-col rounded-xl p-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
            placeholder="Type or paste the script for your voiceover…"
            className="min-h-40 flex-1 resize-none rounded-lg bg-transparent p-2 text-body text-fg outline-none placeholder:text-fg-faint"
          />
          <div className="mt-1 flex items-center justify-between text-caption text-fg-faint">
            <span>{text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters</span>
            {error && <span className="text-danger">{error}</span>}
          </div>

          {/* Engine toggle */}
          <div className="mt-3 flex gap-2">
            {(["edge", "piper"] as const).map((e) => (
              <button
                key={e}
                onClick={() => setEngine(e)}
                aria-pressed={engine === e}
                className={`rounded px-3 py-1.5 text-body-sm transition-colors duration-fast ${
                  engine === e ? "bg-accent/25 text-accent-bright" : "bg-white/5 text-fg-muted hover:bg-white/10"
                }`}
              >
                {e === "edge" ? "Neural voices (online)" : "Offline voices"}
              </button>
            ))}
          </div>

          {/* Voice picker */}
          <div className="mt-3 flex items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search voices or accents…"
              className="min-w-0 flex-1 rounded bg-white/5 px-3 py-1.5 text-body-sm text-fg outline-none placeholder:text-fg-faint focus:bg-white/10"
            />
            {(["", "Female", "Male"] as const).map((g) => (
              <button
                key={g || "all"}
                onClick={() => setGender(g)}
                aria-pressed={gender === g}
                className={`rounded px-2.5 py-1.5 text-caption transition-colors duration-fast ${
                  gender === g ? "bg-accent/25 text-accent-bright" : "bg-white/5 text-fg-muted hover:bg-white/10"
                }`}
              >
                {g || "All"}
              </button>
            ))}
          </div>

          <div className="mt-2 h-44 shrink-0 overflow-y-auto rounded-lg bg-black/10 p-1">
            {engine === "edge" ? (
              voices.edge.length === 0 ? (
                <p className="p-3 text-body-sm text-fg-muted">
                  Neural voice catalog unavailable — check your internet connection, or use Offline voices.
                </p>
              ) : (
                edgeGroups.map(([group, groupVoices]) => (
                  <div key={group}>
                    <div className="sticky top-0 bg-black/30 px-2 py-1 text-caption text-fg-faint backdrop-blur-sm">
                      {group}
                    </div>
                    {groupVoices.map((v) => (
                      <button
                        key={v.id}
                        onClick={() => setVoice(v.id)}
                        aria-pressed={voice === v.id}
                        className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-body-sm transition-colors duration-fast ${
                          voice === v.id ? "bg-accent/25 text-fg" : "text-fg-muted hover:bg-white/5"
                        }`}
                      >
                        <span>{v.name}</span>
                        <span className="text-caption text-fg-faint">{v.gender} · {v.locale}</span>
                      </button>
                    ))}
                  </div>
                ))
              )
            ) : (
              piperFiltered.map((v) => (
                <div
                  key={v.id}
                  className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-body-sm ${
                    voice === v.id ? "bg-accent/25 text-fg" : "text-fg-muted"
                  }`}
                >
                  <button
                    onClick={() => v.installed && setVoice(v.id)}
                    disabled={!v.installed}
                    className="flex-1 text-left disabled:cursor-default"
                  >
                    {v.name}
                    <span className="ml-2 text-caption text-fg-faint">
                      {v.gender} · {v.language}
                    </span>
                  </button>
                  {v.installed ? (
                    <span className="text-caption text-success">installed</span>
                  ) : (
                    <button
                      onClick={() => void downloadPiper(v.id)}
                      disabled={downloading !== null}
                      className="flex items-center gap-1 rounded bg-white/5 px-2 py-1 text-caption text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg disabled:opacity-50"
                    >
                      {downloading === v.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Download className="h-3 w-3" />
                      )}
                      {v.size_mb} MB
                    </button>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Delivery controls */}
          <div className="mt-3 grid grid-cols-3 gap-3">
            {(
              [
                ["Speed", rate, setRate, -50, 100, "%"],
                ["Pitch", pitch, setPitch, -50, 50, "Hz"],
                ["Volume", volume, setVolume, -50, 50, "%"],
              ] as const
            ).map(([label, value, set, min, max, unit]) => (
              <label key={label} className="text-caption text-fg-muted">
                {label}
                <span className="float-right font-mono text-fg-faint">
                  {value > 0 ? "+" : ""}{value}{unit}
                </span>
                <input
                  type="range"
                  min={min}
                  max={max}
                  value={value}
                  onChange={(e) => set(Number(e.target.value))}
                  disabled={engine === "piper" && label !== "Speed" && label !== "Volume"}
                  className="mt-1 block w-full accent-[var(--c-accent)] disabled:opacity-40"
                />
              </label>
            ))}
          </div>

          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={() => void generate()}
              disabled={!canGenerate}
              className="flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-body font-semibold text-white transition-colors duration-fast hover:bg-accent-bright disabled:cursor-not-allowed disabled:opacity-40"
            >
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
              {generating ? "Generating…" : "Generate voiceover"}
            </button>
            <button
              onClick={() => void preview()}
              disabled={!voice || previewing || (engine === "piper" && !selectedPiper?.installed)}
              className="rounded-lg bg-white/5 px-4 py-2.5 text-body text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg disabled:opacity-40"
            >
              {previewing ? "Previewing…" : "Preview voice"}
            </button>
          </div>
        </div>

        {/* Generations */}
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <h2 className="text-h4 text-fg">Generations</h2>
          {items.length === 0 ? (
            <p className="text-body-sm text-fg-muted">
              Nothing generated yet. Write a script, pick a voice, and hit Generate.
            </p>
          ) : (
            items.map((item) => (
              <VoiceoverCard
                key={item.id}
                item={item}
                onDelete={() => {
                  void api.deleteVoiceover(item.id).then(() =>
                    setItems((prev) => prev.filter((v) => v.id !== item.id)),
                  );
                }}
                onReuse={() => {
                  setText(item.text);
                  setEngine(item.engine);
                  setVoice(item.voice);
                  setRate(item.rate);
                  setPitch(item.pitch);
                  setVolume(item.volume);
                }}
              />
            ))
          )}
        </div>
      </div>
    </SectionShell>
  );
}
