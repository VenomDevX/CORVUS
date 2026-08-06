import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Cpu,
  Download,
  Gauge,
  HardDrive,
  KeyRound,
  MonitorSmartphone,
  ChevronLeft,
} from "lucide-react";
import { api, type ProviderInfo, type SystemSpecs } from "../lib/api";
import { pullOllamaModel } from "../lib/ollama";
import { ThinkingAnimation } from "./ThinkingAnimation";

/**
 * First-run setup wizard: welcome → offline model or own API key →
 * device scan + in-app model download → done. Shown once; completion
 * persists in backend settings (onboarding_complete).
 */

type Step = "welcome" | "mode" | "offline" | "apikey" | "done";

const FIT_LABEL = {
  recommended: { text: "Recommended for your device", cls: "text-success" },
  cpu_ok: { text: "Runs on CPU (slower)", cls: "text-warning" },
  too_big: { text: "Too big for this device", cls: "text-danger" },
} as const;

function StepDots({ index }: { index: number }) {
  return (
    <div className="flex gap-1.5" aria-hidden>
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full transition-colors duration-base ${
            i <= index ? "bg-white" : "bg-white/15"
          }`}
        />
      ))}
    </div>
  );
}

export function OnboardingSetup({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState<Step>("welcome");
  const [specs, setSpecs] = useState<SystemSpecs | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [pull, setPull] = useState<{ percent: number; status: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const finish = useCallback(async () => {
    try {
      await api.updateSettings({ onboarding_complete: true });
    } finally {
      onComplete();
    }
  }, [onComplete]);

  const loadSpecs = useCallback(async () => {
    const s = await api.systemSpecs();
    setSpecs(s);
    setModel((current) => current || s.suggested);
    return s;
  }, []);

  // Offline step: fetch specs; while Ollama is missing, re-poll so the wizard
  // advances by itself once the user installs and starts it.
  useEffect(() => {
    if (step !== "offline") return;
    void loadSpecs().catch(() => setError("Couldn't read device specs."));
    pollTimer.current = setInterval(() => {
      void loadSpecs().catch(() => undefined);
    }, 4000);
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [step, loadSpecs]);

  useEffect(() => {
    if (step !== "apikey") return;
    void api
      .listProviders()
      .then((list) => {
        const cloud = list.filter((p) => p.needs_key);
        setProviders(cloud);
        setProvider((current) => current || cloud[0]?.name || "");
      })
      .catch(() => setError("Couldn't load the provider list."));
  }, [step]);

  const installed = new Set(specs?.ollama.models.map((m) => m.name) ?? []);

  async function chooseModel(id: string) {
    setModel(id);
    setError(null);
    setBusy(true);
    try {
      if (!installed.has(id)) {
        setPull({ percent: 0, status: "starting download" });
        await pullOllamaModel(id, setPull);
        setPull(null);
      }
      await api.updateSettings({ provider: "ollama", model: id });
      setStep("done");
    } catch (e) {
      setPull(null);
      setError(e instanceof Error ? e.message : "model download failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveApiKey() {
    if (!provider || !apiKey.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.setProviderKey(provider, apiKey.trim());
      await api.updateSettings({ provider });
      setStep("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't save the key");
    } finally {
      setBusy(false);
    }
  }

  const stepIndex = { welcome: 0, mode: 1, offline: 2, apikey: 2, done: 3 }[step];

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xl">
      <div className="liquid-glass relative flex w-[520px] flex-col items-center gap-5 rounded-2xl p-8">
        {step !== "welcome" && step !== "done" && (
          <button
            onClick={() => {
              if (step === "mode") setStep("welcome");
              else if (step === "offline" || step === "apikey") setStep("mode");
            }}
            className="absolute left-6 top-6 text-fg-muted transition-colors hover:text-fg"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}
        <div className="flex items-center">
          <img src="./logo.png" alt="Corvus" className="h-10 w-10" />
          <span className="-ml-1 text-4xl font-semibold tracking-tight">
            Corvus
          </span>
        </div>

        {step === "welcome" && (
          <>
            <p className="text-center text-body text-fg-muted">
              Your AI assistant that lives on this PC.
              <br />
              Private by default — your conversations never have to leave your machine.
            </p>
            <button
              onClick={() => setStep("mode")}
              className="mt-2 rounded-lg bg-white px-6 py-2.5 text-body font-semibold text-black transition-colors duration-fast hover:bg-white/90"
            >
              Get started
            </button>
          </>
        )}

        {step === "mode" && (
          <>
            <h2 className="text-h3 tracking-tight text-fg">How should Corvus think?</h2>
            <div className="flex w-full flex-col gap-3">
              <button
                onClick={() => setStep("offline")}
                className="rounded-xl border border-accent/40 bg-accent/10 p-4 text-left transition-colors duration-fast hover:bg-accent/20"
              >
                <div className="flex items-center gap-2 text-body font-semibold text-fg">
                  <MonitorSmartphone className="h-4 w-4 text-accent-bright" />
                  Offline model
                  <span className="rounded-sm bg-white/20 px-1.5 py-0.5 text-caption text-white">
                    Recommended
                  </span>
                </div>
                <p className="mt-1 text-body-sm text-fg-muted">
                  Free and private. Corvus scans this PC and suggests a model it can run —
                  downloaded right here in the app.
                </p>
              </button>
              <button
                onClick={() => setStep("apikey")}
                className="rounded-xl border border-white/10 bg-white/5 p-4 text-left transition-colors duration-fast hover:bg-white/10"
              >
                <div className="flex items-center gap-2 text-body font-semibold text-fg">
                  <KeyRound className="h-4 w-4 text-fg-muted" />
                  My own API key
                </div>
                <p className="mt-1 text-body-sm text-fg-muted">
                  Use OpenAI, Anthropic, Gemini, or DeepSeek with your key. Stored encrypted
                  on this PC.
                </p>
              </button>
            </div>
          </>
        )}

        {step === "offline" && (
          <>
            <h2 className="text-h3 tracking-tight text-fg">Your device</h2>
            {!specs ? (
              <ThinkingAnimation text={null} containerClassName="flex items-center justify-center" className="h-8 w-10 text-fg-muted" />
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-body-sm text-fg-muted">
                  <span className="flex items-center gap-1.5">
                    <HardDrive className="h-3.5 w-3.5" /> {specs.ram_gb} GB RAM
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Gauge className="h-3.5 w-3.5" />
                    {specs.gpu ? `${specs.gpu.name} · ${specs.gpu.vram_gb} GB` : "No dedicated GPU"}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Cpu className="h-3.5 w-3.5" /> {specs.cpu_cores} cores
                  </span>
                </div>

                {!specs.ollama.running ? (
                  <div className="flex w-full flex-col items-center gap-3 rounded-xl bg-white/5 p-5 text-center">
                    <p className="text-body-sm text-fg-muted">
                      Corvus runs local models through <strong>Ollama</strong>, which isn't
                      running yet. Install it, and this page will continue automatically.
                    </p>
                    <button
                      onClick={() => void window.corvus?.openExternal("https://ollama.com/download")}
                      className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-body-sm font-semibold text-black transition-colors duration-fast hover:bg-white/90"
                    >
                      <Download className="h-4 w-4" /> Get Ollama
                    </button>
                    <span className="flex items-center text-caption text-fg-faint">
                      <ThinkingAnimation text="waiting for Ollama…" containerClassName="flex flex-row items-center gap-2" className="h-4 w-5" />
                    </span>
                  </div>
                ) : pull ? (
                  <div className="w-full space-y-2">
                    <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full bg-white transition-all duration-base"
                        style={{ width: `${Math.round(pull.percent * 100)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-caption text-fg-muted">
                      <span>Downloading {model} — {pull.status}</span>
                      <span>{Math.round(pull.percent * 100)}%</span>
                    </div>
                    <p className="text-center text-caption text-fg-faint">
                      One-time download. Keep Corvus open.
                    </p>
                  </div>
                ) : (
                  <div className="max-h-64 w-full space-y-1.5 overflow-y-auto pr-1">
                    {specs.catalog.map((m) => {
                      const fit = FIT_LABEL[m.fit];
                      const isInstalled = installed.has(m.id);
                      const disabled = busy || (m.fit === "too_big" && !isInstalled);
                      return (
                        <button
                          key={m.id}
                          onClick={() => void chooseModel(m.id)}
                          disabled={disabled}
                          className={`w-full rounded-xl border p-3 text-left transition-colors duration-fast ${
                            model === m.id
                              ? "border-white/50 bg-white/10"
                              : "border-white/10 bg-white/5 hover:bg-white/10"
                          } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-body-sm font-semibold text-fg">
                              {m.label}
                              {m.id === specs.suggested && (
                                <span className="ml-2 rounded-sm bg-white/20 px-1.5 py-0.5 text-caption text-white">
                                  Suggested
                                </span>
                              )}
                            </span>
                            <span className="shrink-0 text-caption text-fg-faint">
                              {isInstalled ? (
                                <span className="text-success">Installed ✓</span>
                              ) : (
                                `${m.download_gb} GB`
                              )}
                            </span>
                          </div>
                          <div className="mt-0.5 flex items-center justify-between gap-2">
                            <span className="text-caption text-fg-muted">{m.blurb}</span>
                            <span className={`shrink-0 text-caption ${fit.cls}`}>{fit.text}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </>
        )}

        {step === "apikey" && (
          <>
            <h2 className="text-h3 tracking-tight text-fg">Connect your provider</h2>
            <div className="flex w-full flex-col gap-3">
              <div className="flex flex-wrap gap-2">
                {providers.map((p) => (
                  <button
                    key={p.name}
                    onClick={() => setProvider(p.name)}
                    aria-pressed={provider === p.name}
                    className={`rounded px-3 py-1.5 text-body-sm transition-colors duration-fast ${
                      provider === p.name
                        ? "bg-white/20 text-white"
                        : "bg-white/5 text-fg-muted hover:bg-white/10"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste your API key"
                className="w-full rounded-lg bg-white/5 px-3 py-2.5 text-body-sm text-fg outline-none placeholder:text-fg-faint focus:bg-white/10"
              />
              <p className="text-caption text-fg-faint">
                Encrypted with Windows DPAPI and never sent anywhere except the provider itself.
              </p>
              <button
                onClick={() => void saveApiKey()}
                disabled={busy || !provider || !apiKey.trim()}
                className="flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2.5 text-body font-semibold text-black transition-colors duration-fast hover:bg-white/90 disabled:opacity-40"
              >
                {busy && <ThinkingAnimation text={null} containerClassName="flex items-center justify-center" className="h-5 w-6" />}
                Save and continue
              </button>
            </div>
          </>
        )}

        {step === "done" && (
          <>
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-success/15">
              <Check className="h-6 w-6 text-success" />
            </span>
            <h2 className="text-h3 tracking-tight text-fg">Corvus is ready</h2>
            <p className="text-center text-body-sm text-fg-muted">
              Say “Hey Corvus”, type a message, or explore the Voice Studio.
            </p>
            <button
              onClick={() => void finish()}
              className="mt-1 rounded-lg bg-white px-6 py-2.5 text-body font-semibold text-black transition-colors duration-fast hover:bg-white/90"
            >
              Start
            </button>
          </>
        )}

        {error && <p className="text-center text-caption text-danger">{error}</p>}

        <div className="mt-1 flex w-full items-center justify-between">
          <StepDots index={stepIndex} />
          {step !== "done" && (
            <button
              onClick={() => void finish()}
              className="text-caption text-fg-faint transition-colors duration-fast hover:text-fg-muted"
            >
              Skip for now
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
