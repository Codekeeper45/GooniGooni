/**
 * control-panel/ui/RangeSlider.tsx
 * ─────────────────────────────────
 * Reusable custom range slider with gradient track.
 */

interface RangeSliderProps {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}

export function RangeSlider({
  min, max, step, value, onChange, disabled = false,
}: RangeSliderProps) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="relative py-2">
      <div
        className="w-full h-1.5 rounded-full relative"
        style={{ background: "#1C212C" }}
      >
        <div
          className="absolute left-0 top-0 h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: "linear-gradient(90deg, #4F8CFF, #6366F1)",
            boxShadow: "0 0 6px rgba(79,140,255,0.45)",
          }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          disabled={disabled}
          className="absolute inset-0 w-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
          style={{ height: "100%" }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full"
          style={{
            left: `calc(${pct}% - 7px)`,
            background: "#0F1117",
            border: "2px solid #4F8CFF",
            boxShadow: "0 0 8px rgba(79,140,255,0.5)",
            pointerEvents: "none",
          }}
        />
      </div>
    </div>
  );
}
