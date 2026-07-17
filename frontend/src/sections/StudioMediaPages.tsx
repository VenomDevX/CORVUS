import { useCallback, useEffect, useRef, useState } from "react";
import {
  Download,
  Loader2,
  Play,
  Square,
  Trash2,
  Volume2,
  Wand2,
} from "lucide-react";
import {
  api,
  type ImageModel,
  type MediaGeneration,
  type MediaProfile,
} from "../lib/api";
import { useCorvus } from "../state/store";

/* Shared building blocks for the Image / Video / Sound Effects pages —
 * same skeleton as the Speech page: prompt area left, black sidebar right. */

function useMediaData(kind: "image" | "video" | "sfx") {
  const backendOnline = useCorvus((s) => s.backendOnline);
  const [profile, setProfile] = useState<MediaProfile | null>(null);
  const [items, setItems] = useState<MediaGeneration[]>([]);
  const refresh = useCallback(async () => {
    const [p, list] = await Promise.all([api.mediaProfile(), api.listMedia(kind)]);
    setProfile(p);
    setItems(list);
  }, [kind]);
  useEffect(() => {
    if (backendOnline) void refresh().catch(() => undefined);
  }, [backendOnline, refresh]);
  return { backendOnline, profile, items, setItems, refresh };
}

/** Poll a heavy job until done; returns progress + runner. */
function useJob(onDone: (generationId: number) => void) {
  const [percent, setPercent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

  function track(jobId: number) {
    setPercent(0);
    setError(null);
    timer.current = setInterval(() => {
      void api
        .mediaJob(jobId)
        .then((job) => {
          setPercent(job.percent);
          if (job.state !== "running") {
            if (timer.current) clearInterval(timer.current);
            setPercent(null);
            if (job.state === "error") setError(job.error ?? "generation failed");
            else if (job.generation_id != null) onDone(job.generation_id);
          }
        })
        .catch(() => undefined);
    }, 700);
  }
  return { percent, error, setError, track, busy: percent !== null };
}

function PromptPanel({
  placeholder,
  prompt,
  setPrompt,
  onGenerate,
  busy,
  canGenerate,
  percent,
  error,
  children,
}: {
  placeholder: string;
  prompt: string;
  setPrompt: (v: string) => void;
  onGenerate: () => void;
  busy: boolean;
  canGenerate: boolean;
  percent: number | null;
  error: string | null;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 min-h-0 flex-col p-6 lg:p-10">
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value.slice(0, 2000))}
        placeholder={placeholder}
        className="h-36 shrink-0 resize-none bg-transparent p-0 text-xl font-light leading-relaxed text-fg outline-none placeholder:text-fg-muted/50"
      />
      <div className="mt-2 flex items-center justify-between border-t border-white/10 pt-3 text-xs font-medium uppercase tracking-wider text-fg-faint">
        <span>{prompt.length.toLocaleString()} / 2,000 characters</span>
        {error && <span className="text-danger normal-case">{error}</span>}
      </div>
      <div className="mt-4 flex items-center justify-end gap-4">
        {percent !== null && (
          <div className="flex flex-1 items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-white transition-all duration-base"
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="text-xs text-fg-muted">{percent}%</span>
          </div>
        )}
        <button
          onClick={onGenerate}
          disabled={!canGenerate}
          className="flex items-center justify-center gap-2 rounded-xl bg-white px-8 py-3 text-body font-semibold text-black shadow-lg shadow-white/10 transition-all duration-fast hover:bg-white/90 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Wand2 className="h-5 w-5" />}
          {busy ? "Generating…" : "Generate"}
        </button>
      </div>
      <div className="mt-6 min-h-0 flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}

function Sidebar({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex w-full min-h-0 flex-col border-t border-white/10 bg-black lg:w-[420px] lg:border-l lg:border-t-0 xl:w-[460px]">
      <div className="flex-1 overflow-y-auto p-6 text-white">{children}</div>
    </div>
  );
}

function Setting({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-semibold tracking-tight text-fg">{label}</label>
      {children}
    </div>
  );
}

function ChoiceRow<T extends string | number>({
  options,
  value,
  onChange,
  format,
}: {
  options: T[];
  value: T;
  onChange: (v: T) => void;
  format?: (v: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={String(o)}
          onClick={() => onChange(o)}
          className={`rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors ${
            value === o ? "bg-white text-black" : "bg-white/5 text-gray-300 hover:bg-white/10"
          }`}
        >
          {format ? format(o) : String(o)}
        </button>
      ))}
    </div>
  );
}

function ModelCard({
  models,
  onInstalled,
}: {
  models: ImageModel[];
  onInstalled: () => void;
}) {
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  async function install(id: string) {
    setDownloading(true);
    setError("");
    const timer = setInterval(() => {
      void api
        .imageModelDownloadStatus()
        .then((s) => {
          if (s.total_bytes > 0)
            setProgress(
              `${(s.done_bytes / 1e9).toFixed(2)} / ${(s.total_bytes / 1e9).toFixed(2)} GB`,
            );
        })
        .catch(() => undefined);
    }, 1000);
    try {
      await api.downloadImageModel(id);
      onInstalled();
    } catch (e) {
      setError(e instanceof Error ? e.message : "download failed");
    } finally {
      clearInterval(timer);
      setDownloading(false);
      setProgress("");
    }
  }

  return (
    <div className="space-y-2">
      {models.map((m) => (
        <div key={m.id} className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold text-white">{m.label}</span>
            {m.installed ? (
              <span className="text-caption text-success">Installed ✓</span>
            ) : (
              <button
                onClick={() => void install(m.id)}
                disabled={downloading}
                className="flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs font-semibold text-black transition-colors hover:bg-white/90 disabled:opacity-50"
              >
                {downloading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                {downloading ? progress || "Downloading…" : `${m.download_gb} GB`}
              </button>
            )}
          </div>
          <p className="mt-1 text-caption text-gray-500">{m.blurb}</p>
          {error && <p className="mt-1 text-caption text-danger">{error}</p>}
        </div>
      ))}
    </div>
  );
}

function HistoryList({
  items,
  onDelete,
  render,
}: {
  items: MediaGeneration[];
  onDelete: (id: number) => void;
  render: (item: MediaGeneration) => React.ReactNode;
}) {
  if (items.length === 0)
    return <p className="text-sm text-gray-500">Nothing generated yet.</p>;
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.id} className="group rounded-xl border border-white/10 bg-white/5 p-2.5">
          {render(item)}
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <span className="truncate text-caption text-gray-500">{item.prompt}</span>
            <span className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <a
                href={api.mediaFileUrl(item.id)}
                download={item.filename}
                className="rounded p-1 text-gray-400 hover:bg-white/10 hover:text-white"
                aria-label="Download"
              >
                <Download className="h-3.5 w-3.5" />
              </a>
              <button
                onClick={() => onDelete(item.id)}
                className="rounded p-1 text-gray-400 hover:bg-danger/20 hover:text-danger"
                aria-label="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------- Image -------------------------------- */

export function StudioImagePage() {
  const { backendOnline, profile, items, refresh } = useMediaData("image");
  const [models, setModels] = useState<ImageModel[]>([]);
  const [prompt, setPrompt] = useState("");
  const [size, setSize] = useState(512);
  const job = useJob(() => void refresh());

  const loadModels = useCallback(() => void api.imageModels().then(setModels).catch(() => undefined), []);
  useEffect(() => {
    if (backendOnline) loadModels();
  }, [backendOnline, loadModels]);

  useEffect(() => {
    if (profile && size > profile.image_max_size) setSize(profile.image_max_size);
  }, [profile, size]);

  const installed = models.some((m) => m.installed);

  async function generate() {
    if (!prompt.trim()) return;
    try {
      const { job_id } = await api.generateImage({ prompt: prompt.trim(), size });
      job.track(job_id);
    } catch (e) {
      job.setError(e instanceof Error ? e.message : "failed to start");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <PromptPanel
        placeholder="Describe the image you want — subject, style, lighting…"
        prompt={prompt}
        setPrompt={setPrompt}
        onGenerate={() => void generate()}
        busy={job.busy}
        canGenerate={backendOnline && installed && !job.busy && prompt.trim().length > 0}
        percent={job.percent}
        error={job.error ?? (!installed && backendOnline ? "Download the image model in Settings on the right to start." : null)}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {items.map((item) => (
            <img
              key={item.id}
              src={api.mediaFileUrl(item.id)}
              alt={item.prompt}
              title={item.prompt}
              className="aspect-square w-full rounded-xl object-cover ring-1 ring-white/10"
              loading="lazy"
            />
          ))}
        </div>
      </PromptPanel>
      <Sidebar>
        <div className="flex flex-col gap-6">
          <Setting label="Model">
            <ModelCard models={models} onInstalled={loadModels} />
          </Setting>
          <Setting label="Size">
            <ChoiceRow
              options={profile?.image_sizes ?? [384, 512]}
              value={size}
              onChange={setSize}
              format={(s) => `${s}×${s}`}
            />
            <p className="text-caption text-gray-500">
              Capped at {profile?.image_max_size ?? 512}px on this device
              {profile?.gpu_accelerated ? " · GPU accelerated" : " · CPU mode"}.
            </p>
          </Setting>
          <Setting label="History">
            <HistoryList
              items={items}
              onDelete={(id) => void api.deleteMedia(id).then(() => refresh())}
              render={(item) => (
                <img
                  src={api.mediaFileUrl(item.id)}
                  alt=""
                  className="h-20 w-full rounded-lg object-cover"
                  loading="lazy"
                />
              )}
            />
          </Setting>
        </div>
      </Sidebar>
    </div>
  );
}

/* -------------------------------- Video -------------------------------- */

export function StudioVideoPage() {
  const { backendOnline, profile, items, refresh } = useMediaData("video");
  const [models, setModels] = useState<ImageModel[]>([]);
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(4);
  const [motion, setMotion] = useState("zoom");
  const job = useJob(() => void refresh());

  const loadModels = useCallback(() => void api.imageModels().then(setModels).catch(() => undefined), []);
  useEffect(() => {
    if (backendOnline) loadModels();
  }, [backendOnline, loadModels]);

  const installed = models.some((m) => m.installed);

  async function generate() {
    if (!prompt.trim()) return;
    try {
      const { job_id } = await api.generateVideo({ prompt: prompt.trim(), seconds, motion });
      job.track(job_id);
    } catch (e) {
      job.setError(e instanceof Error ? e.message : "failed to start");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <PromptPanel
        placeholder="Describe the scene for your motion clip…"
        prompt={prompt}
        setPrompt={setPrompt}
        onGenerate={() => void generate()}
        busy={job.busy}
        canGenerate={backendOnline && installed && !job.busy && prompt.trim().length > 0}
        percent={job.percent}
        error={job.error ?? (!installed && backendOnline ? "Video uses the image model for keyframes — download it on the Image page first." : null)}
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {items.map((item) => (
            <img
              key={item.id}
              src={api.mediaFileUrl(item.id)}
              alt={item.prompt}
              title={item.prompt}
              className="w-full rounded-xl ring-1 ring-white/10"
              loading="lazy"
            />
          ))}
        </div>
      </PromptPanel>
      <Sidebar>
        <div className="flex flex-col gap-6">
          <Setting label="Duration">
            <ChoiceRow options={[3, 4, 6, 8]} value={seconds} onChange={setSeconds} format={(s) => `${s}s`} />
          </Setting>
          <Setting label="Motion">
            <ChoiceRow options={["zoom", "crossfade"]} value={motion} onChange={setMotion} />
            <p className="text-caption text-gray-500">
              Clips are built from {profile?.video_max_keyframes ?? 3} AI keyframes with smooth
              motion — rendered fully on this PC.
            </p>
          </Setting>
          <Setting label="History">
            <HistoryList
              items={items}
              onDelete={(id) => void api.deleteMedia(id).then(() => refresh())}
              render={(item) => (
                <img src={api.mediaFileUrl(item.id)} alt="" className="w-full rounded-lg" loading="lazy" />
              )}
            />
          </Setting>
        </div>
      </Sidebar>
    </div>
  );
}

/* ----------------------------- Sound Effects ----------------------------- */

export function StudioSfxPage() {
  const { backendOnline, items, refresh } = useMediaData("sfx");
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(3);
  const [intensity, setIntensity] = useState(0.6);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  function play(id: number) {
    if (playingId === id) {
      audioRef.current?.pause();
      setPlayingId(null);
      return;
    }
    audioRef.current?.pause();
    const audio = new Audio(api.mediaFileUrl(id));
    audioRef.current = audio;
    audio.onended = () => setPlayingId(null);
    setPlayingId(id);
    void audio.play();
  }

  async function generate() {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const row = await api.generateSfx({ prompt: prompt.trim(), duration, intensity });
      await refresh();
      play(row.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "generation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <PromptPanel
        placeholder='Describe a sound — "heavy rain with distant thunder", "sci-fi laser zap", "footsteps in a hall"…'
        prompt={prompt}
        setPrompt={setPrompt}
        onGenerate={() => void generate()}
        busy={busy}
        canGenerate={backendOnline && !busy && prompt.trim().length > 0}
        percent={null}
        error={error}
      >
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="group flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3"
            >
              <button
                onClick={() => play(item.id)}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-black transition-transform hover:scale-105"
                aria-label={playingId === item.id ? "Stop" : "Play"}
              >
                {playingId === item.id ? (
                  <Square className="h-4 w-4 fill-current" />
                ) : (
                  <Play className="ml-0.5 h-4 w-4 fill-current" />
                )}
              </button>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-fg">{item.prompt}</div>
                <div className="text-caption text-fg-faint">
                  {String((item.params as { categories?: string[] }).categories?.join(", ") ?? "")}
                  {" · "}
                  {String((item.params as { duration?: number }).duration ?? "")}s
                </div>
              </div>
              <span className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <a
                  href={api.mediaFileUrl(item.id)}
                  download={item.filename}
                  className="rounded p-1.5 text-gray-400 hover:bg-white/10 hover:text-white"
                  aria-label="Download"
                >
                  <Download className="h-4 w-4" />
                </a>
                <button
                  onClick={() => void api.deleteMedia(item.id).then(() => refresh())}
                  className="rounded p-1.5 text-gray-400 hover:bg-danger/20 hover:text-danger"
                  aria-label="Delete"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </span>
            </div>
          ))}
          {items.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-10 text-center text-gray-500">
              <Volume2 className="h-8 w-8 opacity-40" />
              <p className="text-sm">Describe a sound and hit Generate — it renders instantly, fully offline.</p>
            </div>
          )}
        </div>
      </PromptPanel>
      <Sidebar>
        <div className="flex flex-col gap-6">
          <Setting label={`Duration — ${duration}s`}>
            <input
              type="range"
              min={0.5}
              max={10}
              step={0.5}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full accent-white"
            />
          </Setting>
          <Setting label={`Intensity — ${Math.round(intensity * 100)}%`}>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={intensity}
              onChange={(e) => setIntensity(Number(e.target.value))}
              className="w-full accent-white"
            />
          </Setting>
          <p className="text-caption text-gray-500">
            Sounds are synthesized on-device from layered noise and tone generators — instant,
            deterministic with a seed, and always offline. Categories: rain, thunder, wind, ocean,
            fire, explosion, impact, whoosh, laser, UI beeps, footsteps, heartbeat, bells, birds,
            static, engine, ambience.
          </p>
        </div>
      </Sidebar>
    </div>
  );
}
