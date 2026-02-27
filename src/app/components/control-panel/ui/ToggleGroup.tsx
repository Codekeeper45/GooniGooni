/**
 * control-panel/ui/ToggleGroup.tsx
 * ─────────────────────────────────
 * Reusable pill-style toggle group.
 */

interface ToggleGroupProps<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}

export function ToggleGroup<T extends string>({
  options, value, onChange, disabled = false,
}: ToggleGroupProps<T>) {
  return (
    <div className="flex gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => !disabled && onChange(opt.value)}
          disabled={disabled}
          className="flex-1 py-2.5 rounded-xl text-xs transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
          style={
            value === opt.value
              ? {
                  background: "rgba(79,140,255,0.1)",
                  border: "1px solid rgba(79,140,255,0.3)",
                  color: "#4F8CFF",
                }
              : {
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.06)",
                  color: "#6B7280",
                }
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
