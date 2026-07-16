import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label?: string;
  hint?: string;
}

/**
 * Corvus-styled dropdown replacing native <select>: liquid-glass menu,
 * keyboard (Escape/Enter/arrows) + click-outside handling, and automatic
 * upward opening near the bottom of the window (e.g. the chat input bar).
 */
export function Select({
  value,
  options,
  onChange,
  placeholder = "Select…",
  disabled = false,
  className = "",
  compact = false,
  ariaLabel,
}: {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** Borderless caption-sized trigger (chat input bar). */
  compact?: boolean;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [openUp, setOpenUp] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);

  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open && highlighted >= 0) {
      menuRef.current
        ?.querySelectorAll("li")
        [highlighted]?.scrollIntoView({ block: "nearest" });
    }
  }, [open, highlighted]);

  function toggle() {
    if (disabled) return;
    if (!open) {
      const rect = rootRef.current?.getBoundingClientRect();
      // Flip upward when there's less room below than the menu wants.
      setOpenUp(!!rect && window.innerHeight - rect.bottom < 280);
      setHighlighted(options.findIndex((o) => o.value === value));
    }
    setOpen(!open);
  }

  function pick(option: SelectOption) {
    setOpen(false);
    if (option.value !== value) onChange(option.value);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;
    if (e.key === "Escape") setOpen(false);
    else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (open && highlighted >= 0) pick(options[highlighted]);
      else toggle();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return toggle();
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setHighlighted((h) => Math.min(options.length - 1, Math.max(0, h + delta)));
    }
  }

  return (
    <div ref={rootRef} className={`relative ${className}`} onKeyDown={onKeyDown}>
      <button
        type="button"
        onClick={toggle}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        className={
          compact
            ? "flex h-8 max-w-44 items-center gap-1 rounded px-2 text-caption text-fg-muted transition-colors duration-fast hover:bg-white/10 hover:text-fg disabled:opacity-40"
            : "flex w-full items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-left text-body text-fg transition-colors duration-fast hover:bg-white/10 focus:border-accent/60 focus:outline-none disabled:opacity-40"
        }
      >
        <span className="truncate">{selected?.label ?? selected?.value ?? placeholder}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 text-fg-faint transition-transform duration-fast ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <ul
          ref={menuRef}
          role="listbox"
          className={`liquid-glass absolute z-50 max-h-64 w-full min-w-44 overflow-y-auto rounded-xl p-1 ${
            openUp ? "bottom-full mb-1" : "top-full mt-1"
          }`}
        >
          {options.map((option, i) => {
            const isSelected = option.value === value;
            return (
              <li
                key={option.value}
                role="option"
                aria-selected={isSelected}
                onPointerEnter={() => setHighlighted(i)}
                onClick={() => pick(option)}
                className={`flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-body-sm transition-colors duration-fast ${
                  i === highlighted ? "bg-accent/20 text-fg" : "text-fg-muted"
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate">{option.label ?? option.value}</span>
                  {option.hint && (
                    <span className="block truncate text-caption text-fg-faint">{option.hint}</span>
                  )}
                </span>
                {isSelected && <Check className="h-3.5 w-3.5 shrink-0 text-accent-bright" />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
