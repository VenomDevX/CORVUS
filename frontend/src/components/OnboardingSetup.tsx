import { useEffect, useState } from "react";
import { Button, ProgressBar, Spinner } from "@fluentui/react-components";
import { ArrowDownloadRegular, ErrorCircleRegular } from "@fluentui/react-icons";

export function OnboardingSetup({ onComplete }: { onComplete: () => void }) {
  const [status, setStatus] = useState<"checking" | "ollama_missing" | "downloading" | "error" | "success">("checking");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("Checking for default AI model...");
  const [errorMessage, setErrorMessage] = useState("");

  const DEFAULT_MODEL = "qwen2.5-coder:latest";

  useEffect(() => {
    let cancelled = false;

    async function runCheck() {
      try {
        // 1. Check if Ollama is running
        let tagsRes;
        try {
          tagsRes = await fetch("http://127.0.0.1:11434/api/tags");
        } catch {
          if (!cancelled) setStatus("ollama_missing");
          return;
        }

        if (!tagsRes.ok) {
          throw new Error("Failed to check Ollama models.");
        }

        const data = await tagsRes.json();
        const hasModel = data.models?.some((m: any) => m.name === DEFAULT_MODEL);

        if (hasModel) {
          if (!cancelled) {
            setStatus("success");
            onComplete();
          }
          return;
        }

        // 2. Model is missing, start downloading
        if (!cancelled) {
          setStatus("downloading");
          setMessage(`Downloading ${DEFAULT_MODEL}...`);
        }

        const pullRes = await fetch("http://127.0.0.1:11434/api/pull", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: DEFAULT_MODEL }),
        });

        if (!pullRes.ok) throw new Error("Failed to start model download.");
        if (!pullRes.body) throw new Error("No response body.");

        const reader = pullRes.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // keep incomplete line

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const msg = JSON.parse(line);
              if (msg.status === "success") {
                if (!cancelled) {
                  setStatus("success");
                  onComplete();
                }
                return;
              }
              if (msg.error) {
                throw new Error(msg.error);
              }
              if (msg.total && msg.completed) {
                const percent = msg.completed / msg.total;
                if (!cancelled) {
                  setProgress(percent);
                  setMessage(`Downloading model weights...`);
                }
              } else if (msg.status) {
                if (!cancelled) setMessage(msg.status);
              }
            } catch (e) {
              console.error("Failed to parse pull message", line, e);
            }
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setStatus("error");
          setErrorMessage(err.message || "Unknown error occurred.");
        }
      }
    }

    runCheck();
    return () => { cancelled = true; };
  }, [onComplete]);

  // Once complete, the parent should unmount us, so we can return null here for the success state
  if (status === "success") return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xl transition-all">
      <div className="flex w-[480px] flex-col items-center gap-6 rounded-2xl bg-surface p-10 shadow-glass-3">
        <img src="./logo.png" alt="Corvus" className="h-16 w-16" />
        <h2 className="text-xl font-semibold tracking-tight text-fg">Corvus Setup</h2>
        
        {status === "checking" && (
          <div className="flex flex-col items-center gap-4">
            <Spinner appearance="primary" />
            <p className="text-fg-muted">{message}</p>
          </div>
        )}

        {status === "ollama_missing" && (
          <div className="flex flex-col items-center gap-4 text-center">
            <ErrorCircleRegular className="text-warning h-12 w-12" />
            <p className="text-fg-muted">
              Corvus requires <strong>Ollama</strong> to run local AI models. We couldn't detect Ollama running on your system.
            </p>
            <Button
              appearance="primary"
              icon={<ArrowDownloadRegular />}
              onClick={() => {
                // @ts-ignore
                if (window.corvus) {
                  // @ts-ignore
                  window.corvus.openExternal("https://ollama.com/download");
                } else {
                  window.open("https://ollama.com/download", "_blank");
                }
              }}
            >
              Download Ollama
            </Button>
            <p className="text-caption text-fg-faint mt-2">
              Install it, start it, and then restart Corvus.
            </p>
          </div>
        )}

        {status === "downloading" && (
          <div className="flex w-full flex-col items-center gap-4 text-center">
            <div className="w-full space-y-2">
              <ProgressBar value={progress} thickness="large" color="brand" className="w-full" />
              <div className="flex justify-between text-caption text-fg-muted">
                <span>{message}</span>
                <span>{Math.round(progress * 100)}%</span>
              </div>
            </div>
            <p className="text-caption text-fg-faint text-center mt-2 max-w-xs">
              This is a one-time download (approx 4.7 GB). Please keep Corvus open while it downloads the intelligence core.
            </p>
          </div>
        )}

        {status === "error" && (
          <div className="flex flex-col items-center gap-4 text-center">
            <ErrorCircleRegular className="text-danger h-12 w-12" />
            <p className="text-fg-muted">There was an error downloading the model:</p>
            <p className="text-sm text-danger bg-danger/10 p-2 rounded max-h-32 overflow-y-auto">{errorMessage}</p>
            <Button appearance="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
