export interface Attachment {
  name: string;
  size: number;
  type: string;
  url?: string;
  file?: File;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function iconFor(type: string, name: string): string {
  if (type.startsWith("image/")) return "🖼️";
  if (type === "application/pdf" || name.endsWith(".pdf")) return "📄";
  if (/\.(docx?|odt)$/i.test(name)) return "📝";
  if (/\.(xlsx?|csv)$/i.test(name)) return "📊";
  if (/\.(zip|7z|rar)$/i.test(name)) return "🗜️";
  return "📎";
}

export function FileCard({
  attachment,
  onRemove,
}: {
  attachment: Attachment;
  onRemove?: () => void;
}) {
  return (
    <div className="glass flex items-center gap-2 rounded p-2 pr-3">
      {attachment.url ? (
        <img src={attachment.url} alt={attachment.name} className="h-10 w-10 rounded-sm object-cover" />
      ) : (
        <span className="text-h3" aria-hidden>
          {iconFor(attachment.type, attachment.name)}
        </span>
      )}
      <div className="min-w-0">
        <div className="max-w-48 truncate text-body-sm text-fg">{attachment.name}</div>
        <div className="text-caption text-fg-faint">{formatSize(attachment.size)}</div>
      </div>
      {onRemove && (
        <button
          onClick={onRemove}
          aria-label={`Remove ${attachment.name}`}
          className="ml-1 rounded-sm px-1 text-fg-faint transition-colors duration-fast hover:text-danger"
        >
          ✕
        </button>
      )}
    </div>
  );
}
