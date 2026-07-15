import { useRef, useState } from "react";
import { Tooltip } from "@fluentui/react-components";
import { useCorvus } from "../state/store";
import { api } from "../lib/api";
import { FileCard, type Attachment } from "./FileCard";
import { Mic, Image as ImageIcon, Paperclip, Square, Volume2 } from "lucide-react";

export function InputBar() {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const generating = useCorvus((s) => s.generating);
  const backendOnline = useCorvus((s) => s.backendOnline);
  const send = useCorvus((s) => s.send);
  const stopGeneration = useCorvus((s) => s.stopGeneration);
  const setVoiceMode = useCorvus((s) => s.setVoiceMode);
  const pushToTalk = useCorvus((s) => s.pushToTalk);
  const imageInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const [uploading, setUploading] = useState(false);

  async function submit() {
    const body = text.trim();
    if ((!body && attachments.length === 0) || generating || !backendOnline || uploading) return;

    // Upload attachments so agent actions can read them by path, then reference
    // each path in the message so the model can act on it (e.g. describe_image).
    let content = body;
    if (attachments.length > 0) {
      setUploading(true);
      try {
        for (const a of attachments) {
          if (!a.file) continue;
          const { path } = await api.uploadFile(a.file);
          const kind = a.type.startsWith("image/") ? "image" : "file";
          content += `\n\n[Attached ${kind}: ${path}]`;
        }
      } catch {
        content += "\n\n[An attachment failed to upload.]";
      } finally {
        setUploading(false);
      }
    }

    send(content || "(no message)");
    setText("");
    setAttachments([]);
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const next = Array.from(list).map((f) => ({
      name: f.name,
      size: f.size,
      type: f.type || "application/octet-stream",
      url: f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined,
      file: f,
    }));
    setAttachments((prev) => [...prev, ...next]);
  }

  return (
    <div className="glass rounded-lg p-3">
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((a, i) => (
            <FileCard
              key={`${a.name}-${i}`}
              attachment={a}
              onRemove={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
            />
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <Tooltip content="Push to talk" relationship="label">
          <button
            disabled={!backendOnline}
            onClick={() => {
              setVoiceMode(true);
              pushToTalk();
            }}
            aria-label="Push to talk"
            className="rounded p-2 text-fg-muted transition-colors duration-fast enabled:hover:bg-accent/10 enabled:hover:text-fg disabled:cursor-not-allowed disabled:text-fg-faint"
          >
            <Mic className="h-5 w-5" />
          </button>
        </Tooltip>
        <button
          aria-label="Attach image"
          onClick={() => imageInput.current?.click()}
          className="rounded p-2 text-fg-muted transition-colors duration-fast hover:bg-accent/10 hover:text-fg"
        >
          <ImageIcon className="h-5 w-5" />
        </button>
        <button
          aria-label="Attach file"
          onClick={() => fileInput.current?.click()}
          className="rounded p-2 text-fg-muted transition-colors duration-fast hover:bg-accent/10 hover:text-fg"
        >
          <Paperclip className="h-5 w-5" />
        </button>
        <input ref={imageInput} type="file" accept="image/*" multiple hidden onChange={(e) => addFiles(e.target.files)} />
        <input ref={fileInput} type="file" multiple hidden onChange={(e) => addFiles(e.target.files)} />

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={Math.min(6, Math.max(1, text.split("\n").length))}
          placeholder={backendOnline ? "Message Corvus…" : "Corvus core is offline — start the backend"}
          aria-label="Message Corvus"
          className="flex-1 resize-none bg-transparent px-2 py-2 text-body text-fg outline-none placeholder:text-fg-faint"
        />

        {generating ? (
          <button
            onClick={stopGeneration}
            aria-label="Stop generating"
            className="rounded bg-danger/20 px-3 py-2 text-body text-danger transition-colors duration-fast hover:bg-danger/30"
          >
            <span className="flex items-center gap-2"><Square className="h-4 w-4 fill-current" /> Stop</span>
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={(!text.trim() && attachments.length === 0) || !backendOnline || uploading}
            aria-label="Send message"
            className="rounded bg-accent px-4 py-2 text-body font-medium text-white shadow-glow transition-all duration-fast enabled:hover:bg-accent-bright disabled:opacity-40 disabled:shadow-none"
          >
            {uploading ? "Uploading…" : "Send"}
          </button>
        )}

        <Tooltip content="Voice mode" relationship="label">
          <button
            disabled={!backendOnline}
            onClick={() => setVoiceMode(true)}
            aria-label="Enter voice mode"
            className="rounded p-2 text-fg-muted transition-colors duration-fast enabled:hover:bg-accent/10 enabled:hover:text-fg disabled:cursor-not-allowed disabled:text-fg-faint"
          >
            <Volume2 className="h-5 w-5" />
          </button>
        </Tooltip>
      </div>
    </div>
  );
}
