import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { Memory } from "../lib/api";

const CATEGORIES: { key: Memory["category"]; label: string; color: string }[] = [
  { key: "preference", label: "Preferences", color: "#4F8CFF" },
  { key: "project", label: "Projects", color: "#34C77B" },
  { key: "person", label: "People", color: "#C778DD" },
  { key: "app", label: "Apps", color: "#E5A54B" },
];

/** Radial cluster of memories: category hubs around "You", facts fanned around
 * their hub. The schema stores flat facts, so clustering by category is the
 * honest visualization (no invented relations). */
export function MemoryGraph({
  memories,
  onDelete,
}: {
  memories: Memory[];
  onDelete: (id: number) => void;
}) {
  const [selected, setSelected] = useState<Memory | null>(null);
  const size = 640;
  const cx = size / 2;
  const cy = size / 2;

  const layout = useMemo(() => {
    const hubs = CATEGORIES.map((cat, i) => {
      const angle = (i / CATEGORIES.length) * Math.PI * 2 - Math.PI / 2;
      return { ...cat, x: cx + Math.cos(angle) * 150, y: cy + Math.sin(angle) * 150, angle };
    });
    const nodes = memories.map((m) => {
      const hub = hubs.find((h) => h.key === m.category) ?? hubs[0];
      const siblings = memories.filter((x) => x.category === m.category);
      const idx = siblings.findIndex((x) => x.id === m.id);
      // Fan the facts in an arc facing away from the center.
      const spread = Math.min(Math.PI * 1.2, 0.5 * Math.max(siblings.length - 1, 1));
      const a = hub.angle - spread / 2 + (siblings.length > 1 ? (idx / (siblings.length - 1)) * spread : 0);
      const r = 90 + (idx % 3) * 26;
      return { memory: m, hub, x: hub.x + Math.cos(a) * r, y: hub.y + Math.sin(a) * r };
    });
    return { hubs, nodes };
  }, [memories, cx, cy]);

  return (
    <div className="flex flex-col gap-3 lg:flex-row">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="glass mx-auto w-full max-w-xl rounded-lg"
        role="img"
        aria-label="Memory graph grouped by category"
      >
        {/* edges */}
        {layout.hubs.map((h) => (
          <line key={h.key} x1={cx} y1={cy} x2={h.x} y2={h.y} stroke="currentColor" opacity={0.12} />
        ))}
        {layout.nodes.map((n) => (
          <line
            key={`e-${n.memory.id}`}
            x1={n.hub.x}
            y1={n.hub.y}
            x2={n.x}
            y2={n.y}
            stroke={n.hub.color}
            opacity={0.25}
          />
        ))}
        {/* center */}
        <circle cx={cx} cy={cy} r={30} fill="var(--c-accent)" opacity={0.25} />
        <text x={cx} y={cy + 4} textAnchor="middle" className="fill-current text-[13px]">
          You
        </text>
        {/* hubs */}
        {layout.hubs.map((h) => (
          <g key={h.key}>
            <circle cx={h.x} cy={h.y} r={22} fill={h.color} opacity={0.3} />
            <text x={h.x} y={h.y + 4} textAnchor="middle" className="fill-current text-[11px]">
              {h.label}
            </text>
          </g>
        ))}
        {/* memory nodes */}
        {layout.nodes.map((n, i) => (
          <motion.g
            key={n.memory.id}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: Math.min(i * 0.02, 0.4), duration: 0.2 }}
            style={{ cursor: "pointer" }}
            onClick={() => setSelected(n.memory)}
          >
            <circle
              cx={n.x}
              cy={n.y}
              r={selected?.id === n.memory.id ? 10 : 7}
              fill={n.hub.color}
              opacity={selected?.id === n.memory.id ? 0.95 : 0.7}
            >
              <title>{n.memory.content}</title>
            </circle>
          </motion.g>
        ))}
      </svg>

      <div className="glass min-w-64 flex-1 rounded-lg p-4">
        {selected ? (
          <>
            <span
              className="rounded-sm px-1.5 py-0.5 text-caption"
              style={{
                background: `${CATEGORIES.find((c) => c.key === selected.category)?.color}33`,
                color: CATEGORIES.find((c) => c.key === selected.category)?.color,
              }}
            >
              {CATEGORIES.find((c) => c.key === selected.category)?.label}
            </span>
            <p className="mt-2 text-body text-fg">{selected.content}</p>
            <p className="mt-1 text-caption text-fg-faint">
              {new Date(selected.created_at + "Z").toLocaleString()}
            </p>
            <button
              onClick={() => {
                onDelete(selected.id);
                setSelected(null);
              }}
              className="mt-3 rounded bg-danger/15 px-3 py-1.5 text-body-sm text-danger transition-colors duration-fast hover:bg-danger/25"
            >
              Delete this memory
            </button>
          </>
        ) : (
          <p className="text-body-sm text-fg-muted">
            Click a dot to see the stored fact. Facts cluster around their category — the graph shows
            everything Corvus remembers about you at a glance.
          </p>
        )}
      </div>
    </div>
  );
}
