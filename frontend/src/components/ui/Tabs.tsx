/** Underlined tab strip, shared by Tasks and Plugins. */
export function Tabs<T extends string>({
  value,
  onChange,
  tabs,
}: {
  value: T;
  onChange: (v: T) => void;
  tabs: { value: T; label: string }[];
}) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 border-b border-white/10">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={`-mb-px border-b-2 px-3 py-2 text-body-sm transition-colors duration-fast ${
            value === t.value
              ? "border-accent text-fg"
              : "border-transparent text-fg-muted hover:text-fg"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
