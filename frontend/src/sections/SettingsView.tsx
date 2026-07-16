import { useEffect, useState } from "react";
import { Switch } from "@fluentui/react-components";
import { SectionShell } from "./SectionShell";
import { api } from "../lib/api";
import { useCorvus } from "../state/store";
import { Orb } from "../components/Orb";
import { ProviderSettings } from "../components/ProviderSettings";
import { OllamaModels } from "../components/OllamaModels";
import { Select } from "../components/ui/Select";
import { AboutSettings } from "../components/AboutSettings";
import { ORB_STATES, type OrbState } from "../lib/tokens";

const TTS_VOICES = [
  "en-US-AriaNeural",
  "en-US-JennyNeural",
  "en-US-MichelleNeural",
  "en-GB-SoniaNeural",
  "en-AU-NatashaNeural",
];

export function SettingsView() {
  const theme = useCorvus((s) => s.theme);
  const setTheme = useCorvus((s) => s.setTheme);
  const backendOnline = useCorvus((s) => s.backendOnline);
  const voice = useCorvus((s) => s.voice);
  const setWakeEnabled = useCorvus((s) => s.setWakeEnabled);
  const [ttsVoice, setTtsVoice] = useState(TTS_VOICES[0]);
  const [orbPreview, setOrbPreview] = useState<OrbState>("idle");

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
    <SectionShell title="Settings">
      <div className="max-w-2xl space-y-6">
        <section className="glass rounded-lg p-4">
          <h2 className="mb-3 text-h4">About &amp; updates</h2>
          <AboutSettings />
        </section>

        <section className="glass rounded-lg p-4">
          <h2 className="mb-3 text-h4">Appearance</h2>
          <Switch
            checked={theme === "light"}
            onChange={(_e, data) => setTheme(data.checked ? "light" : "dark")}
            label={`Theme: ${theme === "dark" ? "Dark (default)" : "Light"}`}
          />
        </section>

        <section className="glass rounded-lg p-4">
          <h2 className="mb-1 text-h4">AI provider &amp; model</h2>
          <p className="mb-3 text-body-sm text-fg-muted">
            Switch between local Ollama and cloud providers. Keys are stored encrypted on this
            machine.
          </p>
          <ProviderSettings />
        </section>

        <section className="glass rounded-lg p-4">
          <h2 className="mb-1 text-h4">Offline models</h2>
          <p className="mb-3 text-body-sm text-fg-muted">
            Download more local models right here — each is annotated with how well it fits this
            device. Downloads are one-time and everything runs on your PC.
          </p>
          {backendOnline ? (
            <OllamaModels />
          ) : (
            <p className="text-body-sm text-danger">Corvus core is offline.</p>
          )}
        </section>

        <section className="glass rounded-lg p-4">
          <h2 className="mb-1 text-h4">Voice</h2>
          <p className="mb-3 text-body-sm text-fg-muted">
            Wake word runs locally (Whisper tiny). Speech uses Microsoft neural voices online, with
            a Windows offline fallback.
          </p>
          <Switch
            checked={voice.wakeEnabled}
            disabled={!voice.connected}
            onChange={(_e, data) => setWakeEnabled(data.checked)}
            label={`Always listening for “Hey Corvus”: ${voice.wakeEnabled ? "on" : "off"}`}
          />
          <div className="mt-3">
            <label className="mb-1 block text-body-sm text-fg-muted">Voice</label>
            <Select
              className="w-72"
              ariaLabel="Assistant voice"
              value={ttsVoice}
              disabled={!backendOnline}
              onChange={(next) => void changeTtsVoice(next)}
              options={TTS_VOICES.map((v) => ({ value: v }))}
            />
          </div>
        </section>

        <section className="glass rounded-lg p-4">
          <h2 className="mb-1 text-h4">Backend status</h2>
          <p className="text-body">
            {backendOnline ? (
              <span className="text-success">● Corvus core online (127.0.0.1:8765)</span>
            ) : (
              <span className="text-danger">● Corvus core offline</span>
            )}
          </p>
        </section>

        {import.meta.env.DEV && (
          <section className="glass rounded-lg p-4">
            <h2 className="mb-3 text-h4">Orb states (dev preview)</h2>
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
          </section>
        )}
      </div>
    </SectionShell>
  );
}
