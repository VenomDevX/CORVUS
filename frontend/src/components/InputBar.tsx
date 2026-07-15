import { useRef, useState, useEffect, useCallback } from "react";
import { Tooltip } from "@fluentui/react-components";
import { useCorvus } from "../state/store";
import { api } from "../lib/api";
import { FileCard, type Attachment } from "./FileCard";
import { 
  Mic, 
  Image as ImageIcon, 
  Paperclip, 
  Square, 
  Volume2, 
  ArrowUpIcon
} from "lucide-react";
import { cn } from "../lib/utils";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";

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

  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 48,
    maxHeight: 150,
  });

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
    <div className="w-full max-w-3xl mx-auto pb-4">
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
      
      <div className="relative glass rounded-xl shadow-glass-1">
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
              <Button
                variant="ghost"
                size="icon"
                onClick={() => imageInput.current?.click()}
                className="text-neutral-500 dark:text-neutral-400 hover:text-black dark:hover:text-white hover:bg-neutral-200 dark:hover:bg-neutral-700 h-8 w-8"
              >
                <ImageIcon className="w-4 h-4" />
              </Button>
            </Tooltip>
            <Tooltip content="Attach file" relationship="label">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => fileInput.current?.click()}
                className="text-neutral-500 dark:text-neutral-400 hover:text-black dark:hover:text-white hover:bg-neutral-200 dark:hover:bg-neutral-700 h-8 w-8"
              >
                <Paperclip className="w-4 h-4" />
              </Button>
            </Tooltip>
            <Tooltip content="Voice mode" relationship="label">
              <Button
                disabled={!backendOnline}
                variant="ghost"
                size="icon"
                onClick={() => setVoiceMode(true)}
                className="text-neutral-500 dark:text-neutral-400 hover:text-black dark:hover:text-white hover:bg-neutral-200 dark:hover:bg-neutral-700 h-8 w-8 disabled:opacity-30"
              >
                <Volume2 className="w-4 h-4" />
              </Button>
            </Tooltip>
            <Tooltip content="Push to talk" relationship="label">
              <Button
                disabled={!backendOnline}
                variant="ghost"
                size="icon"
                onClick={() => {
                  setVoiceMode(true);
                  pushToTalk();
                }}
                className="text-neutral-500 dark:text-neutral-400 hover:text-black dark:hover:text-white hover:bg-neutral-200 dark:hover:bg-neutral-700 h-8 w-8 disabled:opacity-30"
              >
                <Mic className="w-4 h-4" />
              </Button>
            </Tooltip>
            <input ref={imageInput} type="file" accept="image/*" multiple hidden onChange={(e) => addFiles(e.target.files)} />
            <input ref={fileInput} type="file" multiple hidden onChange={(e) => addFiles(e.target.files)} />
          </div>

          <div className="flex items-center gap-2">
            {generating ? (
              <Button
                onClick={stopGeneration}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 h-8 rounded-lg transition-colors",
                  "bg-danger/20 text-danger hover:bg-danger/30"
                )}
              >
                <Square className="w-4 h-4 fill-current" />
                <span className="text-sm">Stop</span>
              </Button>
            ) : (
              <Button
                onClick={submit}
                disabled={(!text.trim() && attachments.length === 0) || !backendOnline || uploading}
                className={cn(
                  "flex items-center gap-1 px-3 py-1.5 h-8 rounded-lg transition-colors",
                  ((!text.trim() && attachments.length === 0) || !backendOnline || uploading)
                    ? "bg-neutral-200 text-neutral-400 dark:bg-neutral-700 dark:text-neutral-400 cursor-not-allowed"
                    : "bg-black text-white hover:bg-neutral-800 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
                )}
              >
                <ArrowUpIcon className="w-4 h-4" />
                <span className="text-sm">{uploading ? "Uploading..." : "Send"}</span>
              </Button>
            )}
          </div>
        </div>
      </div>


    </div>
  );
}
