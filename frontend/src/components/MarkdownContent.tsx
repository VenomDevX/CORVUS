import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="group relative my-2 overflow-hidden rounded">
      <div className="flex items-center justify-between bg-bg-rein px-3 py-1.5">
        <span className="text-caption text-fg-faint">{language || "code"}</span>
        <button
          onClick={copy}
          aria-label="Copy code"
          className="rounded-sm px-2 py-0.5 text-caption text-fg-muted transition-colors duration-fast hover:bg-accent/20 hover:text-fg"
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: "13px", lineHeight: "20px" }}
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
}

/** Markdown renderer for chat bubbles: GFM tables, code with copy button,
 * inline images, and links that open in the system browser. */
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
                if (href) void (window.corvus?.openExternal(href) ?? window.open(href, "_blank"));
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
