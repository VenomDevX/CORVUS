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
  Sparkles,
  Command,
  Mic,
  ArrowRight
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, type ProviderInfo, type SystemSpecs } from "../lib/api";
import { pullOllamaModel } from "../lib/ollama";
import { ThinkingAnimation } from "./ThinkingAnimation";
import { WebGLBackground } from "./WebGLBackground";

/**
 * First-run setup wizard: welcome → offline model or own API key →
 * device scan + in-app model download → done. Shown once; completion
 * persists in backend settings (onboarding_complete).
 */

type Step = "welcome" | "mode" | "offline" | "apikey" | "tutorial" | "done";

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
  const [installError, setInstallError] = useState<string | null>(null);
  const [installingOllama, setInstallingOllama] = useState(false);
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
      setStep("tutorial");
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
      setStep("tutorial");
    } catch (e) {
      setError(e instanceof Error ? e.message : "couldn't save the key");
    } finally {
      setBusy(false);
    }
  }

  const stepIndex = { welcome: 0, mode: 1, offline: 2, apikey: 2, tutorial: 3, done: 4 }[step];
  const [tutorialSlide, setTutorialSlide] = useState(0);

  /* ─── Hidden Sign-In Code (preserved for future use) ─── */
  const [isLogin, setIsLogin] = useState(true);
  const socialBtn: React.CSSProperties = {
    width:"100%", padding:"0.65rem", borderRadius:6,
    border:"1px solid #333", background:"transparent", color:"#fff",
    fontWeight:500, fontSize:"0.875rem", cursor:"pointer",
    display:"flex", alignItems:"center", justifyContent:"center", gap:"0.5rem",
    marginBottom:"0.4rem",
  };
  const input: React.CSSProperties = {
    width:"100%", padding:"0.65rem 0.85rem", borderRadius:6,
    border:"1px solid #333", background:"#000", color:"#fff",
    fontSize:"0.875rem", outline:"none",
  };
  const GoogleIcon = (
    <svg viewBox="0 0 24 24" style={{width:16,height:16,flexShrink:0}}>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );
  const GitHubIcon = (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{width:16,height:16,flexShrink:0}}>
      <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.699-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.577.688.48C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z"/>
    </svg>
  );
  const AppleIcon = (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{width:16,height:16,flexShrink:0}}>
      <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.04 2.26-.79 3.59-.76 1.56.04 2.88.75 3.65 1.89-3.08 1.75-2.58 5.61.35 6.75-1.01 2.37-2.39 4.39-4.29 4.29zM12.03 7.25c-.15-2.23 1.66-4.07 3.72-4.25.36 2.38-1.92 4.34-3.72 4.25z"/>
    </svg>
  );
  const Logo = (
    <div style={{background:"#111",width:44,height:44,borderRadius:"50%",display:"flex",alignItems:"center",justifyContent:"center",fontWeight:700,fontSize:"1.15rem",marginBottom:"0.75rem",border:"1px solid #333"}}>JS</div>
  );
  const Footer = (
    <div style={{marginTop:"0.85rem",fontSize:"0.75rem",color:"#666",lineHeight:1.5,textAlign:"center"}}>
      By proceeding, you agree to creating a Vercel account<br/>subject to our{" "}
      <a href="#" style={{color:"#888"}}>Terms of Service</a> and <a href="#" style={{color:"#888"}}>Privacy Policy</a>.
    </div>
  );

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center overflow-hidden bg-black">
      {/* WebGL Dot canvas */}
      <WebGLBackground />

      {/* Vignette */}
      <div className="pointer-events-none absolute inset-0 z-10" style={{ background: "radial-gradient(circle at center,rgba(0,0,0,0.75) 0%,rgba(0,0,0,0) 100%)" }} />

      {/* Modal card */}
      <div className="relative z-20 flex w-[520px] flex-col items-center gap-5 rounded-2xl border border-white/5 bg-[#121212] p-8 shadow-[0_10px_40px_rgba(0,0,0,0.8)]">

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
        <div className="flex items-center gap-2.5">
          <img src="./logo.png" alt="Corvus" className="h-9 w-9" />
          <span className="text-3xl font-semibold tracking-tight">
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
              className="mt-2 rounded-lg bg-white px-6 py-2.5 text-body font-semibold text-black shadow-md transition-all duration-300 hover:scale-[1.02] hover:bg-white/90 hover:shadow-lg active:scale-95"
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
                className="rounded-xl border border-accent/40 bg-accent/10 p-4 text-left transition-all duration-300 hover:scale-[1.01] hover:border-accent/60 hover:bg-accent/20 active:scale-[0.98]"
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
                className="rounded-xl border border-white/10 bg-white/5 p-4 text-left transition-all duration-300 hover:scale-[1.01] hover:border-white/20 hover:bg-white/10 active:scale-[0.98]"
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
                  <div className="flex flex-col items-center gap-3">
                    <p className="text-center text-sm text-fg-muted">
                      Corvus runs local models through <strong>Ollama</strong>, which isn't
                      running on this device.
                    </p>
                    <button
                      onClick={async () => {
                        setInstallingOllama(true);
                        setInstallError(null);
                        try {
                          await window.corvus?.installOllama();
                        } catch (e) {
                          console.error(e);
                          setInstallError(e instanceof Error ? e.message : "Installation failed.");
                        } finally {
                          setInstallingOllama(false);
                        }
                      }}
                      disabled={installingOllama}
                      className="flex items-center gap-2 rounded bg-white px-4 py-2 font-medium text-black transition-colors hover:bg-white/90 disabled:opacity-50"
                    >
                      <Download className="h-4 w-4" /> {installingOllama ? "Downloading & Installing..." : "Install Ollama Automatically"}
                    </button>
                    {installError && (
                      <div className="flex flex-col items-center gap-2">
                        <p className="text-sm text-danger">{installError}</p>
                        <button
                          onClick={() => void window.corvus?.openExternal("https://ollama.com/download")}
                          className="text-xs text-accent-bright underline"
                        >
                          Download Manually Instead
                        </button>
                      </div>
                    )}
                    {!installingOllama && !installError && (
                      <ThinkingAnimation text="waiting for Ollama…" containerClassName="flex flex-row items-center gap-2" className="h-4 w-5" />
                    )}
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
                                <span className="text-white">Installed ✓</span>
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

        {step === "tutorial" && (
          <div className="flex flex-col items-center w-full min-h-[300px]">
            <h2 className="text-h3 tracking-tight text-fg mb-6">How to use Corvus</h2>
            <div className="relative w-full h-[180px] flex items-center justify-center">
              <AnimatePresence mode="wait">
                {tutorialSlide === 0 && (
                  <motion.div
                    key="slide0"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.2 }}
                    className="absolute inset-0 flex flex-col items-center text-center gap-4"
                  >
                    <div className="h-16 w-16 rounded-full bg-accent/20 flex items-center justify-center border border-accent/40 shadow-[0_0_15px_rgba(var(--color-accent),0.5)]">
                      <Sparkles className="h-8 w-8 text-accent-bright" />
                    </div>
                    <div>
                      <h3 className="text-body font-semibold text-fg mb-1">Summon Corvus Anywhere</h3>
                      <p className="text-body-sm text-fg-muted max-w-[280px]">
                        Press <kbd className="bg-white/10 px-1.5 py-0.5 rounded border border-white/20 text-fg">Alt</kbd> + <kbd className="bg-white/10 px-1.5 py-0.5 rounded border border-white/20 text-fg">Space</kbd> from any app to bring up the chat overlay instantly.
                      </p>
                    </div>
                  </motion.div>
                )}
                {tutorialSlide === 1 && (
                  <motion.div
                    key="slide1"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.2 }}
                    className="absolute inset-0 flex flex-col items-center text-center gap-4"
                  >
                    <div className="h-16 w-16 rounded-full bg-white/10 flex items-center justify-center border border-white/20">
                      <Command className="h-8 w-8 text-fg" />
                    </div>
                    <div>
                      <h3 className="text-body font-semibold text-fg mb-1">Fast Actions</h3>
                      <p className="text-body-sm text-fg-muted max-w-[280px]">
                        Press <kbd className="bg-white/10 px-1.5 py-0.5 rounded border border-white/20 text-fg">Ctrl</kbd> + <kbd className="bg-white/10 px-1.5 py-0.5 rounded border border-white/20 text-fg">K</kbd> to open the Command Palette. Type to perform actions quickly.
                      </p>
                    </div>
                  </motion.div>
                )}
                {tutorialSlide === 2 && (
                  <motion.div
                    key="slide2"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.2 }}
                    className="absolute inset-0 flex flex-col items-center text-center gap-4"
                  >
                    <div className="h-16 w-16 rounded-full bg-white/10 flex items-center justify-center border border-white/20">
                      <Mic className="h-8 w-8 text-fg" />
                    </div>
                    <div>
                      <h3 className="text-body font-semibold text-fg mb-1">Voice &amp; Media Studio</h3>
                      <p className="text-body-sm text-fg-muted max-w-[300px]">
                        Click the microphone to talk, or open the Studio tab on the left to generate images, voices, and videos locally!
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <div className="flex gap-2 mt-4 mb-6">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className={`h-1.5 rounded-full transition-all duration-300 ${tutorialSlide === i ? 'w-4 bg-accent' : 'w-1.5 bg-white/20'}`}
                />
              ))}
            </div>
            <button
              onClick={() => {
                if (tutorialSlide < 2) {
                  setTutorialSlide(s => s + 1);
                } else {
                  setStep("done");
                }
              }}
              className="flex items-center gap-2 rounded-lg bg-white px-6 py-2.5 text-body font-semibold text-black transition-colors duration-fast hover:bg-white/90"
            >
              {tutorialSlide < 2 ? "Next" : "Got it"}
              {tutorialSlide < 2 && <ArrowRight className="h-4 w-4" />}
            </button>
          </div>
        )}

        {step === "done" && (
          <>
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10">
              <Check className="h-6 w-6 text-white" />
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

        {/* --- Hidden Sign-in Code Section --- */}
        {false && (
          <div style={{ marginTop: "2rem", width: "100%", borderTop: "1px solid #333", paddingTop: "2rem" }}>
            {isLogin ? (
              <div style={{width:"100%",maxWidth:360,margin:"0 auto",display:"flex",flexDirection:"column",alignItems:"center",textAlign:"center"}}>
                {Logo}
                <h1 style={{fontSize:"1.35rem",fontWeight:600,marginBottom:"0.25rem",letterSpacing:"-0.025em"}}>Sign in to Account</h1>
                <p style={{fontSize:"0.85rem",color:"#888",marginBottom:"0.85rem",lineHeight:1.5}}>Sign in to your Account.</p>
                <form onSubmit={e=>e.preventDefault()} style={{width:"100%",display:"flex",flexDirection:"column",gap:"0.65rem"}}>
                  <input style={input} type="email" placeholder="name@work-email.com" required/>
                  <button type="submit" style={{width:"100%",padding:"0.65rem",borderRadius:6,border:"none",background:"#ededed",color:"#000",fontWeight:500,fontSize:"0.875rem",cursor:"pointer"}}>Continue with Email</button>
                </form>
                <div style={{height:1,background:"#222",width:"100%",margin:"0.85rem 0"}}/>
                <button style={socialBtn}>{GoogleIcon}Continue with Google</button>
                <button style={socialBtn}>{GitHubIcon}Continue with GitHub</button>
                <button style={{...socialBtn,marginBottom:0}}>{AppleIcon}Continue with Apple</button>
                <div style={{marginTop:"1.25rem",fontSize:"0.875rem",color:"#888"}}>
                  Don't have an account?{" "}
                  <button onClick={()=>setIsLogin(false)} style={{color:"#fff",fontWeight:500,background:"none",border:"none",padding:0,cursor:"pointer",fontFamily:"inherit",fontSize:"inherit"}}>Sign Up</button>
                </div>
                {Footer}
              </div>
            ) : (
              <div style={{width:"100%",maxWidth:360,margin:"0 auto",display:"flex",flexDirection:"column",alignItems:"center",textAlign:"center"}}>
                {Logo}
                <h1 style={{fontSize:"1.35rem",fontWeight:600,marginBottom:"0.25rem",letterSpacing:"-0.025em"}}>Sign up for Account</h1>
                <p style={{fontSize:"0.85rem",color:"#888",marginBottom:"0.85rem",lineHeight:1.5}}>Create a new account to get started.</p>
                <form onSubmit={e=>e.preventDefault()} style={{width:"100%",display:"flex",flexDirection:"column",gap:"0.65rem"}}>
                  <input style={input} type="text" placeholder="Full Name" required/>
                  <input style={input} type="email" placeholder="name@work-email.com" required/>
                  <button type="submit" style={{width:"100%",padding:"0.65rem",borderRadius:6,border:"none",background:"#ededed",color:"#000",fontWeight:500,fontSize:"0.875rem",cursor:"pointer"}}>Sign Up with Email</button>
                </form>
                <div style={{height:1,background:"#222",width:"100%",margin:"0.85rem 0"}}/>
                <button style={socialBtn}>{GoogleIcon}Sign up with Google</button>
                <button style={socialBtn}>{GitHubIcon}Sign up with GitHub</button>
                <button style={{...socialBtn,marginBottom:0}}>{AppleIcon}Sign up with Apple</button>
                <div style={{marginTop:"1.25rem",fontSize:"0.875rem",color:"#888"}}>
                  Already have an account?{" "}
                  <button onClick={()=>setIsLogin(true)} style={{color:"#fff",fontWeight:500,background:"none",border:"none",padding:0,cursor:"pointer",fontFamily:"inherit",fontSize:"inherit"}}>Sign In</button>
                </div>
                {Footer}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
