/**
 * Direct renderer → Ollama helpers (127.0.0.1:11434; allowed by the CSP).
 * Model pulls stream NDJSON progress frames; we surface percent + status.
 */

const OLLAMA_HTTP = "http://127.0.0.1:11434";

export interface PullProgress {
  percent: number; // 0..1 of the current layer
  status: string;
}

/** Pull a model through Ollama's API, reporting streaming progress. */
export async function pullOllamaModel(
  name: string,
  onProgress: (p: PullProgress) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${OLLAMA_HTTP}/api/pull`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  } catch (err) {
    throw new Error(parseOllamaError(err));
  }
  if (!res.ok || !res.body) throw new Error(parseOllamaError(`Ollama pull failed: ${res.status}`));

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        let msg: { status?: string; error?: string; total?: number; completed?: number };
        try {
          msg = JSON.parse(line);
        } catch {
          continue;
        }
        if (msg.error) throw new Error(msg.error);
        if (msg.status === "success") return;
        onProgress({
          percent: msg.total && msg.completed ? msg.completed / msg.total : 0,
          status: msg.status ?? "downloading",
        });
      }
    }
  } catch (err) {
    throw new Error(parseOllamaError(err));
  }
}

export function parseOllamaError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  const lower = raw.toLowerCase();
  
  if (lower.includes("no such host") || lower.includes("dial tcp") || lower.includes("failed to fetch")) {
    return "Network error: Unable to reach the model registry. Please check your internet connection.";
  }
  if (lower.includes("no space left on device")) {
    return "Not enough disk space to download this model. Please free up some space.";
  }
  if (lower.includes("deadline exceeded") || lower.includes("timeout")) {
    return "Download timed out. Please check your internet connection and try again.";
  }
  if (lower.includes("connection refused")) {
    return "Could not connect to the local Ollama service. Please ensure Ollama is running.";
  }
  
  // Clean up any other generic prefixes from Ollama Go backend
  return raw.replace(/^pull model manifest:\s*/i, "").replace(/^Get "[^"]+":\s*/i, "");
}
