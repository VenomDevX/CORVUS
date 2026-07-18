import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Moon, Plus, RefreshCcw, Play, Plug, Monitor } from "lucide-react";
import { api } from "../lib/api";
import { useCorvus } from "../state/store";
import { NAV_ITEMS } from "./Sidebar";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
  run: () => void | Promise<void>;
}

/** Subsequence fuzzy match: every query char must appear in order. */
function fuzzy(query: string, text: string): boolean {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let i = 0;
  for (const ch of t) {
    if (ch === q[i]) i += 1;
    if (i === q.length) return true;
  }
  return q.length === 0;
}

export function CommandPalette() {
  const open = useCorvus((s) => s.paletteOpen);
  const setOpen = useCorvus((s) => s.setPaletteOpen);
  const setSection = useCorvus((s) => s.setSection);
  const newConversation = useCorvus((s) => s.newConversation);
  const theme = useCorvus((s) => s.theme);
  const setTheme = useCorvus((s) => s.setTheme);
  const backendOnline = useCorvus((s) => s.backendOnline);

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [dynamic, setDynamic] = useState<Command[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Ctrl+K / Cmd+K toggles; Esc closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useCorvus.getState().paletteOpen);
      } else if (e.key === "Escape" && useCorvus.getState().paletteOpen) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  // Workflows and plugins load lazily each time the palette opens.
  useEffect(() => {
    if (!open || !backendOnline) return;
    void (async () => {
      const cmds: Command[] = [];
      try {
        const workflows = await api.listWorkflows();
        for (const w of workflows) {
          cmds.push({
            id: `wf-${w.id}`,
            label: `Run workflow: ${w.name}`,
            hint: `${w.steps.length} steps`,
            icon: <Play className="h-4 w-4" />,
            run: async () => void (await api.runWorkflow(w.name)),
          });
        }
      } catch {
        /* backend hiccup — static commands still work */
      }
      try {
        const plugins = await api.listPlugins();
        for (const p of plugins) {
          cmds.push({
            id: `plugin-${p.id}`,
            label: `${p.enabled ? "Disable" : "Enable"} plugin: ${p.name}`,
            icon: <Plug className="h-4 w-4" />,
            run: async () => {
              if (p.enabled) await api.disablePlugin(p.id);
              else await api.enablePlugin(p.id);
            },
          });
        }
      } catch {
        /* ignore */
      }
      setDynamic(cmds);
    })();
  }, [open, backendOnline]);

  const commands = useMemo<Command[]>(() => {
    const nav: Command[] = NAV_ITEMS.map((item) => ({
      id: `nav-${item.key}`,
      label: `Go to ${item.label}`,
      icon: item.icon,
      run: () => setSection(item.key),
    }));
    return [
      {
        id: "new-chat",
        label: "New chat",
        icon: <Plus className="h-4 w-4" />,
        run: () => {
          newConversation();
          setSection("chat");
        },
      },
      ...nav,
      {
        id: "toggle-theme",
        label: `Switch to ${theme === "dark" ? "light" : "dark"} theme`,
        icon: <Moon className="h-4 w-4" />,
        run: () => setTheme(theme === "dark" ? "light" : "dark"),
      },
      {
        id: "toggle-widget",
        label: "Toggle desktop widget",
        icon: <Monitor className="h-4 w-4" />,
        run: () => void window.corvus?.toggleWidget?.(),
      },
      {
        id: "rerun-setup",
        label: "Re-run first-time setup",
        icon: <RefreshCcw className="h-4 w-4" />,
        run: async () => {
          await api.updateSettings({ onboarding_complete: false });
          window.location.reload();
        },
      },
      ...dynamic,
    ];
  }, [theme, dynamic, newConversation, setSection, setTheme]);

  const filtered = useMemo(
    () => commands.filter((c) => fuzzy(query, c.label)).slice(0, 12),
    [commands, query],
  );

  useEffect(() => setSelected(0), [query]);

  const execute = useCallback(
    (cmd: Command) => {
      setOpen(false);
      void cmd.run();
    },
    [setOpen],
  );

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && filtered[selected]) {
      e.preventDefault();
      execute(filtered[selected]);
    }
  }

  useEffect(() => {
    listRef.current?.children[selected]?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[95] flex items-start justify-center bg-black/40 pt-[18vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <motion.div
            className="liquid-glass w-full max-w-lg rounded-xl p-2"
            initial={{ opacity: 0, scale: 0.98, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -6 }}
            transition={{ duration: 0.14, ease: "easeOut" }}
            role="dialog"
            aria-label="Command palette"
          >
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onInputKey}
              placeholder="Type a command…"
              className="w-full rounded bg-transparent px-3 py-2.5 text-body text-fg placeholder:text-fg-faint focus:outline-none"
            />
            <ul ref={listRef} className="max-h-72 overflow-y-auto border-t border-white/10 pt-1">
              {filtered.length === 0 && (
                <li className="px-3 py-2 text-body-sm text-fg-muted">No matching commands.</li>
              )}
              {filtered.map((cmd, i) => (
                <li key={cmd.id}>
                  <button
                    onClick={() => execute(cmd)}
                    onMouseEnter={() => setSelected(i)}
                    className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-body-sm transition-colors duration-fast ${
                      i === selected ? "bg-white/10 text-fg" : "text-fg-muted hover:bg-white/5"
                    }`}
                  >
                    <span aria-hidden className="text-fg-faint">{cmd.icon}</span>
                    <span className="flex-1 truncate">{cmd.label}</span>
                    {cmd.hint && <span className="text-caption text-fg-faint">{cmd.hint}</span>}
                  </button>
                </li>
              ))}
            </ul>
            <div className="border-t border-white/10 px-3 pb-1 pt-1.5 text-caption text-fg-faint">
              ↑↓ navigate · Enter run · Esc close
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
