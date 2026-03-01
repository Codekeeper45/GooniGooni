/**
 * control-panel/sections/QuickPresetsSection.tsx
 * ─────────────────────────────────────────────────
 * Duration and aspect ratio quick-select presets.
 */

import type { GenerationType } from "../types";

const DURATION_PRESETS = [
  { label: "3с\nбыстро", seconds: 3 },
  { label: "5с\nстандарт ★", seconds: 5 },
  { label: "8с\nдинамика", seconds: 8 },
  { label: "10с\nэпик", seconds: 10 },
];

const ASPECT_PRESETS = [
  { label: "📱 9:16", width: 720, height: 1280 },
  { label: "🖥 16:9", width: 1280, height: 720 },
  { label: "⬛ 1:1", width: 1024, height: 1024 },
  { label: "📱 4:5", width: 896, height: 1120 },
  { label: "🌊 16:10", width: 1152, height: 720 },
];

interface Props {
  generationType: GenerationType;
  numFrames: number;
  setNumFrames: (n: number) => void;
  fps: number;
  width: number;
  height: number;
  setWidth: (w: number) => void;
  setHeight: (h: number) => void;
  useAdvancedSettings: boolean;
  disabled: boolean;
}

export function QuickPresetsSection({
  generationType, numFrames, setNumFrames, fps, width, height,
  setWidth, setHeight, useAdvancedSettings, disabled,
}: Props) {
  const derivedDurationSec = Math.round((numFrames - 1) / fps);
  const activeAspect = ASPECT_PRESETS.find((p) => p.width === width && p.height === height);

  const handleDurationPreset = (seconds: number) => {
    if (disabled) return;
    const raw = seconds * fps;
    let nFrames = Math.round(raw / 4) * 4 + 1;
    if (nFrames > 201) nFrames = 201;
    setNumFrames(nFrames);
  };

  return (
    <div
      className="rounded-2xl p-4 space-y-4"
      style={{
        background: "rgba(79,140,255,0.03)",
        border: "1px solid rgba(79,140,255,0.08)",
        opacity: useAdvancedSettings ? 0.4 : 1,
        pointerEvents: useAdvancedSettings ? "none" : "auto",
      }}
    >
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-widest" style={{ color: "#6B7280" }}>
          ⚡ Быстрые настройки
        </p>
        {useAdvancedSettings && (
          <span
            className="text-[9px] px-2 py-0.5 rounded-full"
            style={{ background: "rgba(251,191,36,0.15)", color: "#FBD38D", border: "1px solid rgba(251,191,36,0.3)" }}
          >
            Не в приоритете
          </span>
        )}
      </div>

      {/* Duration — video only */}
      {generationType === "video" && (
        <div>
          <p className="text-[10px] mb-2.5" style={{ color: "#4B5563" }}>⏱ Длительность видео</p>
          <div className="grid grid-cols-4 gap-1.5">
            {DURATION_PRESETS.map((preset) => {
              const isActive = derivedDurationSec === preset.seconds;
              return (
                <button
                  key={preset.seconds}
                  onClick={() => handleDurationPreset(preset.seconds)}
                  disabled={disabled || useAdvancedSettings}
                  className="py-2.5 rounded-xl text-[11px] leading-tight transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed whitespace-pre-line"
                  style={
                    isActive
                      ? { background: "rgba(79,140,255,0.15)", border: "1px solid rgba(79,140,255,0.45)", color: "#4F8CFF", boxShadow: "0 0 10px rgba(79,140,255,0.2)" }
                      : { background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", color: "#6B7280" }
                  }
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Aspect ratio */}
      <div>
        <p className="text-[10px] mb-2.5" style={{ color: "#4B5563" }}>📐 Соотношение сторон</p>
        <div className="flex flex-wrap gap-1.5">
          {ASPECT_PRESETS.map((preset) => {
            const isActive = activeAspect?.width === preset.width && activeAspect?.height === preset.height;
            return (
              <button
                key={`${preset.width}x${preset.height}`}
                onClick={() => { if (!disabled) { setWidth(preset.width); setHeight(preset.height); } }}
                disabled={disabled || useAdvancedSettings}
                className="flex-1 min-w-[calc(20%-6px)] py-2.5 rounded-xl text-[11px] transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                style={
                  isActive
                    ? { background: "rgba(79,140,255,0.15)", border: "1px solid rgba(79,140,255,0.45)", color: "#4F8CFF", boxShadow: "0 0 10px rgba(79,140,255,0.2)" }
                    : { background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", color: "#6B7280" }
                }
              >
                {preset.label}
              </button>
            );
          })}
        </div>

        {/* Current resolution display */}
        <div
          className="mt-3 rounded-xl p-3.5"
          style={{ background: "rgba(79,140,255,0.08)", border: "1px solid rgba(79,140,255,0.2)" }}
        >
          <div className="flex items-center justify-between">
            <p className="text-[10px]" style={{ color: "#6B7280" }}>Текущее разрешение:</p>
            {activeAspect && (
              <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: "rgba(79,140,255,0.15)", color: "#4F8CFF" }}>
                {activeAspect.label.split(" ")[1]}
              </span>
            )}
          </div>
          <p className="text-xl font-medium mt-1" style={{ color: "#4F8CFF" }}>{width} × {height}</p>
        </div>
      </div>
    </div>
  );
}
