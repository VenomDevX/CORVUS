import { useRef, useState, useEffect, useCallback } from "react";
import { Tooltip } from "@fluentui/react-components";
import { useCorvus } from "../state/store";
import { api } from "../lib/api";
import { FileCard, type Attachment } from "./FileCard";
import { 
  Mic, 
  Image as ImageIcon, 
  Paperclip, 
  Volume2, 
  ArrowUp
} from "lucide-react";
import { cn } from "../lib/utils";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";
import { Select } from "./ui/Select";

interface AutoResizeProps {
  minHeight: number;
  maxHeight?: number;
}

function useAutoResizeTextarea({ minHeight, maxHeight }: AutoResizeProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`; // reset first
      const newHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Infinity)
      );
      textarea.style.height = `${newHeight}px`;
    },
    [minHeight, maxHeight]
  );

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.style.height = `${minHeight}px`;
  }, [minHeight]);

  return { textareaRef, adjustHeight };
}



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
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);

  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 48,
    maxHeight: 150,
  });

  // Active model + the provider's catalog for the inline picker.
  useEffect(() => {
    if (!backendOnline) return;
    void (async () => {
      try {
        const [settings, list] = await Promise.all([api.getSettings(), api.listModels()]);
        setModel(settings.model ?? "");
        setModels(list.models);
      } catch {
        setModels([]);
      }
    })();
  }, [backendOnline]);

  async function changeModel(next: string) {
    setModel(next);
    try {
      await api.updateSettings({ model: next });
    } catch {
      /* picker is best-effort; Settings has the full editor */
    }
  }

  async function submit() {
    const body = text.trim();
    if ((!body && attachments.length === 0) || generating || !backendOnline || uploading) return;

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
    adjustHeight(true);
  }

  // Full-window drag-and-drop: counter-based so child enter/leave events
  // don't flicker the overlay; drop anywhere attaches like the buttons do.
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth += 1;
      setDragging(true);
    };
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      addFiles(e.dataTransfer?.files ?? null);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const MAX_SIZE = 50 * 1024 * 1024; // 50MB
    const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf", "text/plain", "text/markdown", "text/csv"];
    
    const validFiles = Array.from(list).filter((f) => {
      if (f.size > MAX_SIZE) {
        console.warn(`File ${f.name} exceeds the 50MB limit.`);
        return false;
      }
      if (!ALLOWED_TYPES.includes(f.type) && !f.type.startsWith("image/")) {
        console.warn(`File type ${f.type} is not supported.`);
        return false;
      }
      return true;
    });

    const next = validFiles.map((f) => ({
      name: f.name,
      size: f.size,
      type: f.type || "application/octet-stream",
      url: f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined,
      file: f,
    }));
    setAttachments((prev) => [...prev, ...next]);
  }



  return (
    <div className="w-full max-w-3xl mx-auto pb-4">
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center bg-black/40">
          <div className="liquid-glass rounded-xl px-8 py-6 text-center">
            <Paperclip className="mx-auto mb-2 h-6 w-6 text-accent-bright" />
            <div className="text-body font-semibold text-fg">Drop files to attach</div>
            <div className="text-caption text-fg-muted">Images, PDF, text — up to 50 MB each</div>
          </div>
        </div>
      )}
      {attachments.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {attachments.map((a, i) => (
            <FileCard
              key={`${a.name}-${i}`}
              attachment={a}
              onRemove={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
            />
          ))}
        </div>
      )}
      
      <div className="relative liquid-glass rounded-xl">
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            adjustHeight();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={!backendOnline}
          placeholder={backendOnline ? "Message Corvus..." : "Corvus core is offline — start the backend"}
          className={cn(
            "w-full px-4 py-3 resize-none border-none",
            "transition-[height] duration-150 ease-out",
            "bg-transparent text-black dark:text-white text-sm",
            "focus-visible:ring-0 focus-visible:ring-offset-0",
            "placeholder:text-neutral-500 dark:placeholder:text-neutral-400 min-h-[48px]"
          )}
          style={{ overflow: "hidden" }}
        />

        {/* Footer Buttons */}
        <div className="flex items-center justify-between p-3 pt-0">
          <div className="flex items-center gap-1">
            <Tooltip content="Attach image" relationship="label">
              <button
                type="button"
                onClick={() => imageInput.current?.click()}
                className="flex items-center justify-center text-fg-muted hover:text-fg hover:bg-white/10 rounded h-8 w-8 transition-colors disabled:opacity-30 disabled:pointer-events-none"
              >
                <ImageIcon className="w-4 h-4 pointer-events-none" />
              </button>
            </Tooltip>
            <Tooltip content="Attach file" relationship="label">
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="flex items-center justify-center text-fg-muted hover:text-fg hover:bg-white/10 rounded h-8 w-8 transition-colors disabled:opacity-30 disabled:pointer-events-none"
              >
                <Paperclip className="w-4 h-4 pointer-events-none" />
              </button>
            </Tooltip>
            <Tooltip content="Voice mode" relationship="label">
              <button
                type="button"
                disabled={!backendOnline}
                onClick={() => setVoiceMode(true)}
                className="flex items-center justify-center text-fg-muted hover:text-fg hover:bg-white/10 rounded h-8 w-8 transition-colors disabled:opacity-30 disabled:pointer-events-none"
              >
                <Volume2 className="w-4 h-4 pointer-events-none" />
              </button>
            </Tooltip>
            <Tooltip content="Push to talk" relationship="label">
              <button
                type="button"
                disabled={!backendOnline}
                onClick={() => {
                  setVoiceMode(true);
                  pushToTalk();
                }}
                className="flex items-center justify-center text-fg-muted hover:text-fg hover:bg-white/10 rounded h-8 w-8 transition-colors disabled:opacity-30 disabled:pointer-events-none"
              >
                <Mic className="w-4 h-4 pointer-events-none" />
              </button>
            </Tooltip>
            <input ref={imageInput} type="file" accept="image/*" multiple hidden onChange={(e) => addFiles(e.target.files)} />
            <input ref={fileInput} type="file" multiple hidden onChange={(e) => addFiles(e.target.files)} />
            {models.length > 0 && (
              <Select
                compact
                className="ml-1"
                ariaLabel="Model"
                value={model}
                onChange={(next) => void changeModel(next)}
                options={(models.includes(model) ? models : [model, ...models])
                  .filter(Boolean)
                  .map((m) => ({ value: m }))}
              />
            )}
          </div>

          <div className="flex items-center gap-2">
            {generating ? (
              <Button
                variant={null}
                size={null}
                onClick={stopGeneration}
                className={cn(
                  "flex items-center justify-center h-8 w-8 rounded-lg transition-colors",
                  "bg-black text-white hover:bg-neutral-800 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
                )}
                title="Stop generation"
              >
                <div className="w-3 h-3 rounded-sm bg-current" />
              </Button>
            ) : (
              <Button
                variant={null}
                size={null}
                onClick={submit}
                disabled={(!text.trim() && attachments.length === 0) || !backendOnline || uploading}
                className={cn(
                  "flex items-center justify-center h-8 w-8 rounded-lg transition-colors",
                  ((!text.trim() && attachments.length === 0) || !backendOnline || uploading)
                    ? "bg-neutral-200 text-neutral-400 dark:bg-neutral-700 dark:text-neutral-400 cursor-not-allowed"
                    : "bg-black text-white hover:bg-neutral-800 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
                )}
                title={uploading ? "Uploading..." : "Send message"}
              >
                <ArrowUp className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      </div>


    </div>
  );
}
