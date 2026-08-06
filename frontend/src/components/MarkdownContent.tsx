import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const codeBlock = (
    <div className="group relative my-4 flex flex-col rounded-md bg-black/40 border border-white/10 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-1.5 bg-black/60 border-b border-white/10 text-xs text-fg-muted font-mono select-none">
        <span>{language || "text"}</span>
        <button 
          onClick={copyCode} 
          className="flex items-center gap-1.5 hover:text-fg transition-colors"
          title="Copy code"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied!" : "Copy code"}
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        <SyntaxHighlighter
          language={language || "text"}
          style={oneDark}
          customStyle={{ margin: 0, backgroundColor: 'transparent', background: 'transparent', padding: 0, fontSize: "13px", lineHeight: "20px" }}
          codeTagProps={{ style: { backgroundColor: 'transparent', background: 'transparent' } }}
        >
          {value}
        </SyntaxHighlighter>
      </div>
    </div>
  );

  return codeBlock;
}

/** Markdown renderer for chat bubbles: GFM tables, code with copy button,
 * inline images, and links that open in the system browser. */

function isSafeUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown space-y-2 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-white/10 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-white/10 [&_th]:bg-white/5 [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a
              href={href}
              onClick={(e) => {
                e.preventDefault();
                if (isSafeUrl(href)) {
                  void (window.corvus?.openExternal(href!) ?? window.open(href, "_blank"));
                } else {
                  console.warn(`Blocked unsafe URL: ${href}`);
                }
              }}
              className="text-accent-bright underline decoration-accent/40 hover:decoration-accent-bright"
            >
              {children}
            </a>
          ),
          img: ({ src, alt }) => (
            <img src={src ?? ""} alt={alt ?? ""} className="max-h-80 rounded" />
          ),
          code: (props) => {
            const { className, children } = props;
            const match = /language-(\w+)/.exec(className ?? "");
            const value = String(children).replace(/\n$/, "");
            const inline = !className && !value.includes("\n");
            if (inline) {
              return (
                <code className="rounded-sm bg-white/10 px-1 py-0.5 font-mono text-mono">
                  {value}
                </code>
              );
            }
            return <CodeBlock language={match?.[1] ?? ""} value={value} />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
