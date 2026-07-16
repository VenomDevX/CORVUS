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
  const res = await fetch(`${OLLAMA_HTTP}/api/pull`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok || !res.body) throw new Error(`Ollama pull failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

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
}
