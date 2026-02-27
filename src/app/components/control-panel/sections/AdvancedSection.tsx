/**
 * control-panel/sections/AdvancedSection.tsx
 * ─────────────────────────────────────────────
 * Advanced settings area: toggle, negative prompt, seed,
 * width/height, and model-specific video/image params.
 */

import { RotateCcw, Settings, ChevronDown, ChevronUp, Wand2, Sparkles, Shuffle } from "lucide-react";
import { AnimatePresence } from "motion/react";
import { motion } from "motion/react";
import { RangeSlider } from "../ui/RangeSlider";
import { ToggleGroup } from "../ui/ToggleGroup";
import { ParamLabel } from "../ui/ParamLabel";
import type { GenerationType, VideoModel, ImageModel, VideoMode, ImageMode } from "../types";

interface Props {
  generationType: GenerationType;
  videoModel: VideoModel;
  imageModel: ImageModel;
  videoMode: VideoMode;
  imageMode: ImageMode;

  // Advanced settings enable/disable
  useAdvancedSettings: boolean;
  setUseAdvancedSettings: (v: boolean) => void;
  showAdvanced: boolean;
  setShowAdvanced: (v: boolean) => void;
  onResetAdvanced: () => void;

  // Common params
  negativePrompt: string;
  setNegativePrompt: (v: string) => void;
  seed: number;
  setSeed: (v: number) => void;
  width: number;
  setWidth: (v: number) => void;
  height: number;
  setHeight: (v: number) => void;

  // Video params
  numFrames: number;
  setNumFrames: (v: number) => void;
  fps: number;
  setFps: (v: number) => void;
  motionScore: number;
  setMotionScore: (v: number) => void;
  lightingVariant: "high_noise" | "low_noise";
  setLightingVariant: (v: "high_noise" | "low_noise") => void;
  referenceStrength: number;
  setReferenceStrength: (v: number) => void;

  // Image params
  imageSteps: number;
  setImageSteps: (v: number) => void;
  cfgScaleImage: number;
  setCfgScaleImage: (v: number) => void;
  clipSkip: number;
  setClipSkip: (v: number) => void;
  sampler: string;
  setSampler: (v: string) => void;
  imageGuidanceScale: number;
  setImageGuidanceScale: (v: number) => void;
  imgDenoisingStrength: number;
  setImgDenoisingStrength: (v: number) => void;

  disabled: boolean;
}

export function AdvancedSection({
  generationType, videoModel, imageModel, videoMode, imageMode,
  useAdvancedSettings, setUseAdvancedSettings, showAdvanced, setShowAdvanced, onResetAdvanced,
  negativePrompt, setNegativePrompt,
  seed, setSeed, width, setWidth, height, setHeight,
  numFrames, setNumFrames, fps, setFps,
  motionScore, setMotionScore, lightingVariant, setLightingVariant,
  referenceStrength, setReferenceStrength,
  imageSteps, setImageSteps, cfgScaleImage, setCfgScaleImage,
  clipSkip, setClipSkip, sampler, setSampler,
  imageGuidanceScale, setImageGuidanceScale,
  imgDenoisingStrength, setImgDenoisingStrength,
  disabled,
}: Props) {
  return (
    <div className="space-y-3">
      {/* Toggle row */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowAdvanced((p) => !p)}
          className="flex-1 flex items-center gap-2 text-xs transition-colors duration-150 px-3 py-2 rounded-lg"
          style={{ color: showAdvanced ? "#4F8CFF" : "#6B7280", background: showAdvanced ? "rgba(79,140,255,0.06)" : "transparent" }}
        >
          <Settings className="w-3.5 h-3.5" />
          Advanced settings
          {showAdvanced ? <ChevronUp className="w-3.5 h-3.5 ml-auto" /> : <ChevronDown className="w-3.5 h-3.5 ml-auto" />}
        </button>
        <button
          onClick={onResetAdvanced}
          disabled={disabled}
          className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg transition-all duration-150 disabled:opacity-50"
          style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)", color: "#6B7280" }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(79,140,255,0.35)"; e.currentTarget.style.color = "#4F8CFF"; e.currentTarget.style.background = "rgba(79,140,255,0.06)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)"; e.currentTarget.style.color = "#6B7280"; e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>По умолчанию</span>
        </button>
      </div>

      {/* Expanded panel */}
      <AnimatePresence>
        {showAdvanced && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden space-y-5"
          >
            {/* Enable/disable advanced toggle */}
            <div
              className="rounded-xl p-3 flex items-center justify-between"
              style={{
                background: useAdvancedSettings ? "rgba(79,140,255,0.08)" : "rgba(255,255,255,0.02)",
                border: `1px solid ${useAdvancedSettings ? "rgba(79,140,255,0.25)" : "rgba(255,255,255,0.06)"}`,
              }}
            >
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: useAdvancedSettings ? "rgba(79,140,255,0.15)" : "rgba(255,255,255,0.03)", border: `1px solid ${useAdvancedSettings ? "rgba(79,140,255,0.3)" : "rgba(255,255,255,0.08)"}` }}>
                  <Wand2 className="w-4 h-4" style={{ color: useAdvancedSettings ? "#4F8CFF" : "#6B7280" }} />
                </div>
                <div>
                  <p className="text-xs font-medium" style={{ color: useAdvancedSettings ? "#4F8CFF" : "#E5E7EB" }}>Использовать Advanced</p>
                  <p className="text-[10px]" style={{ color: "#6B7280" }}>{useAdvancedSettings ? "Приоритет у точных настроек" : "Приоритет у быстрых пресетов"}</p>
                </div>
              </div>
              <button
                onClick={() => setUseAdvancedSettings(!useAdvancedSettings)}
                disabled={disabled}
                className="relative w-11 h-6 rounded-full transition-all duration-200 disabled:opacity-50"
                style={{ background: useAdvancedSettings ? "#4F8CFF" : "rgba(255,255,255,0.1)", border: `1px solid ${useAdvancedSettings ? "#4F8CFF" : "rgba(255,255,255,0.15)"}` }}
              >
                <div className="absolute top-0.5 w-5 h-5 rounded-full transition-all duration-200" style={{ left: useAdvancedSettings ? "calc(100% - 22px)" : "2px", background: "#FFFFFF", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }} />
              </button>
            </div>

            {/* Preview mode banner */}
            {!useAdvancedSettings && (
              <div className="rounded-xl p-3 flex items-start gap-2" style={{ background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.2)" }}>
                <Sparkles className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "#FBD38D" }} />
                <div>
                  <p className="text-xs font-medium mb-1" style={{ color: "#FBD38D" }}>Просмотр режим</p>
                  <p className="text-[10px] leading-relaxed" style={{ color: "#9CA3AF" }}>Advanced настройки видны, но не используются при генерации. Приоритет у быстрых пресетов. Включите toggle выше для использования.</p>
                </div>
              </div>
            )}

            {/* Fields wrapper (dim when not in advanced mode) */}
            <div style={{ opacity: useAdvancedSettings ? 1 : 0.4, pointerEvents: useAdvancedSettings ? "auto" : "none" }}>
              {/* Negative Prompt */}
              <ParamLabel>Negative Prompt</ParamLabel>
              <textarea
                value={negativePrompt}
                onChange={(e) => setNegativePrompt(e.target.value)}
                placeholder="What to exclude..."
                rows={2}
                disabled={disabled || !useAdvancedSettings}
                className="w-full rounded-xl px-3.5 py-3 text-sm resize-none outline-none transition-colors duration-150 placeholder-[#374151] disabled:opacity-50"
                style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#9CA3AF", fontFamily: "'Space Grotesk', sans-serif" }}
              />

              {/* Seed */}
              <div className="mt-5">
                <ParamLabel>Seed</ParamLabel>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={seed === -1 ? "" : seed}
                    onChange={(e) => setSeed(e.target.value === "" ? -1 : parseInt(e.target.value))}
                    placeholder="Random (-1)"
                    disabled={disabled || !useAdvancedSettings}
                    className="flex-1 rounded-xl px-3.5 py-2.5 text-sm outline-none placeholder-[#374151] disabled:opacity-50 min-w-0"
                    style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#E5E7EB", fontFamily: "'Space Grotesk', sans-serif" }}
                  />
                  <button
                    onClick={() => setSeed(Math.floor(Math.random() * 2147483647))}
                    disabled={disabled || !useAdvancedSettings}
                    className="p-2.5 rounded-xl transition-all duration-150 disabled:opacity-50"
                    style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#6B7280" }}
                  >
                    <Shuffle className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Width × Height */}
              <div className="mt-5">
                <ParamLabel>Width × Height (точная настройка)</ParamLabel>
                <div className="grid grid-cols-2 gap-3">
                  {([["Width", width, setWidth], ["Height", height, setHeight]] as const).map(([label, val, setter]) => (
                    <div key={label}>
                      <p className="text-xs mb-1.5" style={{ color: "#4B5563" }}>{label}</p>
                      <input
                        type="number"
                        value={val}
                        onChange={(e) => (setter as (v: number) => void)(Number(e.target.value))}
                        min={256}
                        max={2048}
                        step={64}
                        disabled={disabled || !useAdvancedSettings}
                        className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
                        style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#E5E7EB", fontFamily: "'Space Grotesk', sans-serif" }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ── VIDEO-SPECIFIC ── */}
            {generationType === "video" && (
              <div className="rounded-2xl p-4 space-y-4" style={{ background: "rgba(79,140,255,0.03)", border: "1px solid rgba(79,140,255,0.1)", opacity: useAdvancedSettings ? 1 : 0.4, pointerEvents: useAdvancedSettings ? "auto" : "none" }}>
                <p className="text-xs font-medium" style={{ color: "#4F8CFF" }}>Video Parameters</p>

                {/* Num Frames */}
                <div>
                  <div className="flex justify-between mb-1">
                    <p className="text-xs" style={{ color: "#6B7280" }}>Num Frames</p>
                    <span className="text-xs" style={{ color: "#4F8CFF" }}>{numFrames} (~{(numFrames / fps).toFixed(1)}s)</span>
                  </div>
                  <RangeSlider min={16} max={161} step={1} value={numFrames} onChange={setNumFrames} disabled={disabled || !useAdvancedSettings} />
                </div>

                {/* FPS */}
                <div>
                  <ParamLabel>FPS</ParamLabel>
                  <ToggleGroup options={[{ value: "8", label: "8" }, { value: "16", label: "16" }, { value: "24", label: "24" }]} value={String(fps)} onChange={(v) => setFps(Number(v))} disabled={disabled || !useAdvancedSettings} />
                </div>

                {/* Model-specific param */}
                {videoModel === "anisora" ? (
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>Motion Score</p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>{motionScore.toFixed(1)}</span>
                    </div>
                    <RangeSlider min={0} max={5} step={0.1} value={motionScore} onChange={setMotionScore} disabled={disabled || !useAdvancedSettings} />
                  </div>
                ) : (
                  <div>
                    <ParamLabel>Lighting Variant</ParamLabel>
                    <ToggleGroup options={[{ value: "low_noise", label: "Low Noise" }, { value: "high_noise", label: "High Noise" }]} value={lightingVariant} onChange={setLightingVariant} disabled={disabled || !useAdvancedSettings} />
                  </div>
                )}

                {/* Reference strength */}
                {(videoMode === "i2v" || videoMode === "first_last_frame") && (
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>Reference Strength</p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>{referenceStrength.toFixed(2)}</span>
                    </div>
                    <RangeSlider min={0} max={1} step={0.05} value={referenceStrength} onChange={setReferenceStrength} disabled={disabled || !useAdvancedSettings} />
                  </div>
                )}

                <p className="text-[10px]" style={{ color: "#6B7280" }}>
                  {videoModel === "anisora" ? "⚠️ Steps: 8 (fixed), Guidance: 1.0 (optimal)" : "⚠️ Steps: 4 (fixed), CFG: 1.0 (required)"}
                </p>
              </div>
            )}

            {/* ── IMAGE-SPECIFIC ── */}
            {generationType === "image" && (
              <div className="rounded-2xl p-4 space-y-4" style={{ background: "rgba(79,140,255,0.03)", border: "1px solid rgba(79,140,255,0.1)", opacity: useAdvancedSettings ? 1 : 0.4, pointerEvents: useAdvancedSettings ? "auto" : "none" }}>
                <p className="text-xs font-medium" style={{ color: "#4F8CFF" }}>Image Parameters</p>

                {/* Steps */}
                <div>
                  <div className="flex justify-between mb-1">
                    <p className="text-xs" style={{ color: "#6B7280" }}>Steps</p>
                    <span className="text-xs" style={{ color: "#4F8CFF" }}>{imageSteps}</span>
                  </div>
                  <RangeSlider min={10} max={50} step={1} value={imageSteps} onChange={setImageSteps} disabled={disabled || !useAdvancedSettings} />
                </div>

                {/* CFG / Guidance */}
                {imageModel === "pony" ? (
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>CFG Scale</p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>{cfgScaleImage.toFixed(1)}</span>
                    </div>
                    <RangeSlider min={1} max={20} step={0.5} value={cfgScaleImage} onChange={setCfgScaleImage} disabled={disabled || !useAdvancedSettings} />
                  </div>
                ) : (
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>Guidance Scale</p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>{imageGuidanceScale.toFixed(1)}</span>
                    </div>
                    <RangeSlider min={1} max={10} step={0.5} value={imageGuidanceScale} onChange={setImageGuidanceScale} disabled={disabled || !useAdvancedSettings} />
                  </div>
                )}

                {/* Sampler */}
                <div>
                  <ParamLabel>Sampler</ParamLabel>
                  <select
                    value={sampler}
                    onChange={(e) => setSampler(e.target.value)}
                    disabled={disabled || !useAdvancedSettings}
                    className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
                    style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#E5E7EB", fontFamily: "'Space Grotesk', sans-serif" }}
                  >
                    {imageModel === "pony" ? (
                      <>
                        <option value="Euler a">Euler a</option>
                        <option value="DPM++ 2M Karras">DPM++ 2M Karras</option>
                        <option value="DPM++ SDE Karras">DPM++ SDE Karras</option>
                      </>
                    ) : (
                      <>
                        <option value="Euler">Euler</option>
                        <option value="Euler a">Euler a</option>
                        <option value="DPM++ 2M">DPM++ 2M</option>
                      </>
                    )}
                  </select>
                </div>

                {/* Clip Skip (Pony only) */}
                {imageModel === "pony" && (
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>Clip Skip</p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>{clipSkip}</span>
                    </div>
                    <RangeSlider min={1} max={4} step={1} value={clipSkip} onChange={setClipSkip} disabled={disabled || !useAdvancedSettings} />
                  </div>
                )}

                {/* Denoising (img2img) */}
                {imageMode === "img2img" && (
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>Denoising Strength</p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>{imgDenoisingStrength.toFixed(2)}</span>
                    </div>
                    <RangeSlider min={0} max={1} step={0.05} value={imgDenoisingStrength} onChange={setImgDenoisingStrength} disabled={disabled || !useAdvancedSettings} />
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
