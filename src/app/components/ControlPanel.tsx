import { useState, useRef, useCallback } from "react";
import type React from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Video,
  Image as ImageLucide,
  Upload,
  X,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Shuffle,
  Wand2,
  Sparkles,
  RotateCcw,
  Settings,
} from "lucide-react";
import { configManager } from "../utils/configManager";

export type GenerationType = "image" | "video";
export type VideoModel = "anisora" | "phr00t";
export type ImageModel = "pony" | "flux";
export type VideoMode = "t2v" | "i2v" | "first_last_frame" | "arbitrary_frame";
export type ImageMode = "txt2img" | "img2img";
export type GenerationStatus = "idle" | "generating" | "done" | "error";

export interface ArbitraryFrameItem {
  id: string;
  frameIndex: number;
  image: string;
}

export interface ControlPanelProps {
  // Type & Model
  generationType: GenerationType;
  setGenerationType: (t: GenerationType) => void;
  videoModel: VideoModel;
  setVideoModel: (m: VideoModel) => void;
  imageModel: ImageModel;
  setImageModel: (m: ImageModel) => void;
  
  // Mode
  videoMode: VideoMode;
  setVideoMode: (m: VideoMode) => void;
  imageMode: ImageMode;
  setImageMode: (m: ImageMode) => void;
  
  // Advanced Settings Control
  useAdvancedSettings: boolean;
  setUseAdvancedSettings: (u: boolean) => void;
  
  // Common params
  prompt: string;
  setPrompt: (p: string) => void;
  negativePrompt: string;
  setNegativePrompt: (p: string) => void;
  width: number;
  setWidth: (w: number) => void;
  height: number;
  setHeight: (h: number) => void;
  seed: number;
  setSeed: (s: number) => void;
  outputFormat: string;
  setOutputFormat: (f: string) => void;
  
  // Reference images (single)
  referenceImage: string | null;
  onImageUpload: (data: string) => void;
  onImageRemove: () => void;
  
  // Multiple frame references (for first_last_frame and arbitrary_frame)
  firstFrameImage: string | null;
  lastFrameImage: string | null;
  onFirstFrameUpload: (data: string) => void;
  onLastFrameUpload: (data: string) => void;
  onFirstFrameRemove: () => void;
  onLastFrameRemove: () => void;
  
  // Arbitrary frame items
  arbitraryFrames: ArbitraryFrameItem[];
  onArbitraryFrameAdd: (frameIndex: number, image: string) => void;
  onArbitraryFrameRemove: (id: string) => void;
  onArbitraryFrameUpdate: (id: string, frameIndex: number) => void;
  
  // Video params
  numFrames: number;
  setNumFrames: (n: number) => void;
  videoSteps: number;
  setVideoSteps: (s: number) => void;
  guidanceScale: number;
  setGuidanceScale: (g: number) => void;
  fps: number;
  setFps: (f: number) => void;
  motionScore: number;
  setMotionScore: (m: number) => void;
  cfgScaleVideo: number;
  setCfgScaleVideo: (c: number) => void;
  referenceStrength: number;
  setReferenceStrength: (r: number) => void;
  lightingVariant: "high_noise" | "low_noise";
  setLightingVariant: (l: "high_noise" | "low_noise") => void;
  denoisingStrength: number;
  setDenoisingStrength: (d: number) => void;
  
  // Image params
  imageSteps: number;
  setImageSteps: (s: number) => void;
  cfgScaleImage: number;
  setCfgScaleImage: (c: number) => void;
  clipSkip: number;
  setClipSkip: (c: number) => void;
  sampler: string;
  setSampler: (s: string) => void;
  imageGuidanceScale: number;
  setImageGuidanceScale: (g: number) => void;
  imgDenoisingStrength: number;
  setImgDenoisingStrength: (d: number) => void;
  
  // Actions
  onGenerate: () => void;
  status: GenerationStatus;
  estSeconds: number;
}

// ─── Inline slider ────────────────────────────────────────────────────────────
function RangeSlider({
  min,
  max,
  step,
  value,
  onChange,
  disabled = false,
}: {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
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

// ─── Toggle button group ──────────────────────────────────────────────────────
function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
  disabled = false,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
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

// ─── Image Uploader Component ─────────────────────────────────────────────────
function ImageUploader({
  image,
  onUpload,
  onRemove,
  fileRef,
  label,
  disabled = false,
}: {
  image: string | null;
  onUpload: (data: string) => void;
  onRemove: () => void;
  fileRef: React.RefObject<HTMLInputElement>;
  label?: string;
  disabled?: boolean;
}) {
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (disabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (ev) => onUpload(ev.target?.result as string);
      reader.readAsDataURL(file);
    }
  };

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (ev) => onUpload(ev.target?.result as string);
    reader.readAsDataURL(file);
  };

  return (
    <div>
      {label && <ParamLabel>{label}</ParamLabel>}
      {image ? (
        <div
          className="relative rounded-xl overflow-hidden"
          style={{ border: "1px solid rgba(79,140,255,0.2)" }}
        >
          <img
            src={image}
            alt={label || "Reference"}
            className="w-full h-36 object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
          <div className="absolute bottom-2.5 right-2.5 flex gap-1.5">
            <button
              onClick={() => !disabled && fileRef.current?.click()}
              disabled={disabled}
              className="p-1.5 rounded-lg transition-all duration-150 disabled:opacity-50"
              style={{
                background: "rgba(0,0,0,0.5)",
                backdropFilter: "blur(8px)",
                color: "#9CA3AF",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => !disabled && onRemove()}
              disabled={disabled}
              className="p-1.5 rounded-lg transition-all duration-150 disabled:opacity-50"
              style={{
                background: "rgba(0,0,0,0.5)",
                backdropFilter: "blur(8px)",
                color: "#EF4444",
                border: "1px solid rgba(239,68,68,0.2)",
              }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => !disabled && fileRef.current?.click()}
          className="rounded-xl flex flex-col items-center gap-3 py-8 cursor-pointer transition-all duration-200 group"
          style={{
            border: "2px dashed rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.01)",
            opacity: disabled ? 0.5 : 1,
          }}
          onMouseEnter={(e) => {
            if (!disabled) {
              e.currentTarget.style.borderColor = "rgba(79,140,255,0.25)";
              e.currentTarget.style.background = "rgba(79,140,255,0.02)";
            }
          }}
          onMouseLeave={(e) => {
            if (!disabled) {
              e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)";
              e.currentTarget.style.background = "rgba(255,255,255,0.01)";
            }
          }}
        >
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{
              background: "rgba(79,140,255,0.06)",
              border: "1px solid rgba(79,140,255,0.12)",
            }}
          >
            <Upload className="w-4 h-4" style={{ color: "#4F8CFF" }} />
          </div>
          <div className="text-center">
            <p className="text-sm" style={{ color: "#9CA3AF" }}>
              Drop image or{" "}
              <span style={{ color: "#4F8CFF" }}>click to upload</span>
            </p>
            <p className="text-xs mt-1" style={{ color: "#4B5563" }}>
              PNG, JPG, WebP
            </p>
          </div>
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        className="hidden"
      />
    </div>
  );
}

function ParamLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[11px] uppercase tracking-widest mb-2.5"
      style={{ color: "#6B7280", fontFamily: "'Space Grotesk', sans-serif" }}
    >
      {children}
    </p>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export function ControlPanel(props: ControlPanelProps) {
  const {
    generationType, setGenerationType,
    videoModel, setVideoModel,
    imageModel, setImageModel,
    videoMode, setVideoMode,
    imageMode, setImageMode,
    useAdvancedSettings, setUseAdvancedSettings,
    prompt, setPrompt,
    negativePrompt, setNegativePrompt,
    width, setWidth,
    height, setHeight,
    seed, setSeed,
    outputFormat, setOutputFormat,
    
    // Reference images (single)
    referenceImage, onImageUpload, onImageRemove,
    
    // Multiple frame references (for first_last_frame and arbitrary_frame)
    firstFrameImage, lastFrameImage,
    onFirstFrameUpload, onLastFrameUpload,
    onFirstFrameRemove, onLastFrameRemove,
    
    // Arbitrary frame items
    arbitraryFrames, onArbitraryFrameAdd, onArbitraryFrameRemove, onArbitraryFrameUpdate,
    
    // Video params
    numFrames, setNumFrames,
    videoSteps, setVideoSteps,
    guidanceScale, setGuidanceScale,
    fps, setFps,
    motionScore, setMotionScore,
    cfgScaleVideo, setCfgScaleVideo,
    referenceStrength, setReferenceStrength,
    lightingVariant, setLightingVariant,
    denoisingStrength, setDenoisingStrength,
    
    // Image params
    imageSteps, setImageSteps,
    cfgScaleImage, setCfgScaleImage,
    clipSkip, setClipSkip,
    sampler, setSampler,
    imageGuidanceScale, setImageGuidanceScale,
    imgDenoisingStrength, setImgDenoisingStrength,
    
    // Actions
    onGenerate, status, estSeconds,
  } = props;

  const [showAdvanced, setShowAdvanced] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const firstFrameRef = useRef<HTMLInputElement>(null);
  const lastFrameRef = useRef<HTMLInputElement>(null);
  const arbitraryFrameRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [promptFocused, setPromptFocused] = useState(false);
  const [newArbitraryFrameIndex, setNewArbitraryFrameIndex] = useState(40);

  const isGenerating = status === "generating";
  const anisoraFixed = configManager.getFixedParameters("anisora");
  const phr00tFixed = configManager.getFixedParameters("phr00t");
  const anisoraStepsDefault = Number(anisoraFixed.steps?.value ?? 8);
  const anisoraGuidanceDefault = Number(anisoraFixed.guidance_scale?.value ?? 1.0);
  const phr00tStepsDefault = Number(phr00tFixed.steps?.value ?? 4);
  const phr00tCfgDefault = Number(phr00tFixed.cfg_scale?.value ?? 1.0);

  // ─── Quick preset data ───────────────────────────────────────────────────────
  const DURATION_PRESETS = [
    { label: "3с\nбыстро", seconds: 3 },
    { label: "5с\nстандарт ★", seconds: 5 },
    { label: "8с\nдинамика", seconds: 8 },
    { label: "10с\nэпик", seconds: 10 },
  ];

  const ASPECT_PRESETS = [
    { label: "📱 9:16", width: 720, height: 1280 },
    { label: "🖥 16:9", width: 1280, height: 720 },
    { label: "⬛ 1:1", width: 896, height: 896 },
    { label: "📱 4:5", width: 896, height: 1120 },
    { label: "🌊 16:10", width: 1152, height: 720 },
  ];

  // Derive which duration/aspect preset is currently active
  const derivedDurationSec = Math.round((numFrames - 1) / fps);
  const activeAspect = ASPECT_PRESETS.find((p) => p.width === width && p.height === height);

  const handleDurationPreset = (seconds: number) => {
    if (isGenerating) return;
    const raw = seconds * fps;
    let nFrames = Math.round(raw / 4) * 4 + 1;
    if (nFrames > 201) nFrames = 201;
    setNumFrames(nFrames);
  };

  const handleAspectPreset = (w: number, h: number) => {
    if (isGenerating) return;
    setWidth(w);
    setHeight(h);
  };

  // ─── Reset Advanced Settings to model defaults ───────────────────────────────
  const handleResetAdvanced = () => {
    if (isGenerating) return;
    
    // Reset only advanced parameters
    setNegativePrompt("");
    setSeed(-1);
    setOutputFormat("mp4");
    
    if (generationType === "video") {
      const anisoraSteps = Number(anisoraFixed.steps?.value ?? 8);
      const anisoraGuidance = Number(anisoraFixed.guidance_scale?.value ?? 1.0);
      const phr00tSteps = Number(phr00tFixed.steps?.value ?? 4);
      const phr00tCfg = Number(phr00tFixed.cfg_scale?.value ?? 1.0);
      // Reset video advanced params
      setNumFrames(81);
      setFps(16);
      setGuidanceScale(anisoraGuidance);
      setVideoSteps(videoModel === "anisora" ? anisoraSteps : phr00tSteps);
      setMotionScore(3.0);
      setReferenceStrength(videoModel === "anisora" ? 0.85 : 1.0);
      setDenoisingStrength(0.7);
      setCfgScaleVideo(phr00tCfg);
      setLightingVariant("low_noise");
      setWidth(720);
      setHeight(1280);
    } else {
      // Reset image advanced params
      setImageSteps(imageModel === "pony" ? 30 : 25);
      setCfgScaleImage(6.0);
      setImageGuidanceScale(3.5);
      setClipSkip(2);
      setSampler(imageModel === "pony" ? "Euler a" : "Euler");
      setImgDenoisingStrength(0.7);
      setWidth(512);
      setHeight(512);
    }
    
    // Note: Prompt and quick presets are NOT reset
  };

  const handleImageFile = (file: File, callback: (data: string) => void) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (ev) => callback(ev.target?.result as string);
    reader.readAsDataURL(file);
  };

  const handleDrop = useCallback((e: React.DragEvent, callback: (data: string) => void) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleImageFile(file, callback);
  }, []);

  // Validation
  const needsReferenceImage = 
    (generationType === "video" && videoMode === "i2v") ||
    (generationType === "image" && imageMode === "img2img");

  const needsFirstLastFrames = 
    generationType === "video" && videoMode === "first_last_frame";

  const needsArbitraryFrames = 
    generationType === "video" && videoMode === "arbitrary_frame";

  const canGenerate =
    !isGenerating && 
    prompt.trim().length > 0 && 
    (!needsReferenceImage || !!referenceImage) &&
    (!needsFirstLastFrames || (firstFrameImage && lastFrameImage)) &&
    (!needsArbitraryFrames || arbitraryFrames.length > 0);

  const currentModel = generationType === "video" 
    ? (videoModel === "anisora" ? "AniSora V3.2" : "Phr00t WAN 2.2")
    : (imageModel === "pony" ? "Pony V6 XL" : "Flux.1 dev");

  return (
    <div
      className="h-full flex flex-col flex-shrink-0"
      style={{
        width: "clamp(340px, 460px, 460px)",
        background: "#151922",
        borderRight: "1px solid rgba(255,255,255,0.06)",
        fontFamily: "'Space Grotesk', sans-serif",
      }}
    >
      {/* ── Scrollable content ─────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 scroll-smooth">

        {/* ═══════════════════════════════════════════════════════════════════
            TYPE SELECTION (Image vs Video)
        ═══════════════════════════════════════════════════════════════════ */}
        <div
          className="grid grid-cols-2 gap-1 p-1 rounded-xl"
          style={{
            background: "#1C212C",
            border: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          {[
            { id: "image" as GenerationType, icon: ImageLucide, label: "Image" },
            { id: "video" as GenerationType, icon: Video, label: "Video" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => !isGenerating && setGenerationType(tab.id)}
              disabled={isGenerating}
              className="flex items-center justify-center gap-2 py-2.5 px-2 rounded-lg text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              style={
                generationType === tab.id
                  ? {
                      background: "#151922",
                      border: "1px solid rgba(79,140,255,0.2)",
                      color: "#E5E7EB",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                    }
                  : {
                      background: "transparent",
                      border: "1px solid transparent",
                      color: "#4B5563",
                    }
              }
            >
              <tab.icon className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate text-sm">{tab.label}</span>
            </button>
          ))}
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            MODEL SELECTION
        ═══════════════════════════════════════════════════════════════════ */}
        <div>
          <ParamLabel>Model</ParamLabel>
          {generationType === "video" ? (
            <ToggleGroup
              options={[
                { value: "anisora", label: "AniSora V3.2" },
                { value: "phr00t", label: "Phr00t WAN 2.2" },
              ]}
              value={videoModel}
              onChange={setVideoModel}
              disabled={isGenerating}
            />
          ) : (
            <ToggleGroup
              options={[
                { value: "pony", label: "Pony V6 XL" },
                { value: "flux", label: "Flux.1 dev" },
              ]}
              value={imageModel}
              onChange={setImageModel}
              disabled={isGenerating}
            />
          )}
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            MODE SELECTION
        ═══════════════════════════════════════════════════════════════════ */}
        <div>
          <ParamLabel>Mode</ParamLabel>
          {generationType === "video" ? (
            <ToggleGroup
              options={[
                { value: "t2v", label: "Text2Video" },
                { value: "i2v", label: "Image2Video" },
                { value: "first_last_frame", label: "First+Last" },
                ...(videoModel === "anisora" ? [{ value: "arbitrary_frame" as VideoMode, label: "Arbitrary" }] : []),
              ]}
              value={videoMode}
              onChange={setVideoMode}
              disabled={isGenerating}
            />
          ) : (
            <ToggleGroup
              options={[
                { value: "txt2img", label: "Text to Image" },
                { value: "img2img", label: "Image to Image" },
              ]}
              value={imageMode}
              onChange={setImageMode}
              disabled={isGenerating}
            />
          )}
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            QUICK PRESETS
        ═══════════════════════════════════════════════════════════════════ */}
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
            <p
              className="text-[10px] uppercase tracking-widest"
              style={{ color: "#6B7280" }}
            >
              ⚡ Быстрые настройки
            </p>
            {useAdvancedSettings && (
              <span className="text-[9px] px-2 py-0.5 rounded-full" style={{ 
                background: "rgba(251,191,36,0.15)", 
                color: "#FBD38D",
                border: "1px solid rgba(251,191,36,0.3)"
              }}>
                Не в приоритете
              </span>
            )}
          </div>

          {/* Duration presets — video only */}
          {generationType === "video" && (
            <div>
              <p className="text-[10px] mb-2.5" style={{ color: "#4B5563" }}>
                ⏱ Длительность видео
              </p>
              <div className="grid grid-cols-4 gap-1.5">
                {DURATION_PRESETS.map((preset) => {
                  const isActive = derivedDurationSec === preset.seconds;
                  return (
                    <button
                      key={preset.seconds}
                      onClick={() => handleDurationPreset(preset.seconds)}
                      disabled={isGenerating || useAdvancedSettings}
                      className="py-2.5 rounded-xl text-[11px] leading-tight transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed whitespace-pre-line"
                      style={
                        isActive
                          ? {
                              background: "rgba(79,140,255,0.15)",
                              border: "1px solid rgba(79,140,255,0.45)",
                              color: "#4F8CFF",
                              boxShadow: "0 0 10px rgba(79,140,255,0.2)",
                            }
                          : {
                              background: "rgba(255,255,255,0.02)",
                              border: "1px solid rgba(255,255,255,0.07)",
                              color: "#6B7280",
                            }
                      }
                    >
                      {preset.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Aspect ratio presets */}
          <div>
            <p className="text-[10px] mb-2.5" style={{ color: "#4B5563" }}>
              📐 Соотношение сторон
            </p>
            <div className="flex flex-wrap gap-1.5">
              {ASPECT_PRESETS.map((preset) => {
                const isActive = activeAspect?.width === preset.width && activeAspect?.height === preset.height;
                return (
                  <button
                    key={`${preset.width}x${preset.height}`}
                    onClick={() => handleAspectPreset(preset.width, preset.height)}
                    disabled={isGenerating || useAdvancedSettings}
                    className="flex-1 min-w-[calc(20%-6px)] py-2.5 rounded-xl text-[11px] transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                    style={
                      isActive
                        ? {
                            background: "rgba(79,140,255,0.15)",
                            border: "1px solid rgba(79,140,255,0.45)",
                            color: "#4F8CFF",
                            boxShadow: "0 0 10px rgba(79,140,255,0.2)",
                          }
                        : {
                            background: "rgba(255,255,255,0.02)",
                            border: "1px solid rgba(255,255,255,0.07)",
                            color: "#6B7280",
                          }
                    }
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
            
            {/* Current Resolution Display */}
            <div 
              className="mt-3 rounded-xl p-3.5"
              style={{
                background: "rgba(79,140,255,0.08)",
                border: "1px solid rgba(79,140,255,0.2)",
              }}
            >
              <div className="flex items-center justify-between">
                <p className="text-[10px]" style={{ color: "#6B7280" }}>
                  Текущее разрешение:
                </p>
                {activeAspect && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ 
                    background: "rgba(79,140,255,0.15)", 
                    color: "#4F8CFF" 
                  }}>
                    {activeAspect.label.split(" ")[1]}
                  </span>
                )}
              </div>
              <p className="text-xl font-medium mt-1" style={{ color: "#4F8CFF" }}>
                {width} × {height}
              </p>
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            PROMPT
        ═══════════════════════════════════════════════════════════════════ */}
        <div>
          <ParamLabel>Prompt</ParamLabel>
          <div
            className="rounded-xl overflow-hidden transition-all duration-200"
            style={{
              background: "#1C212C",
              border: `1px solid ${promptFocused ? "rgba(79,140,255,0.4)" : "rgba(255,255,255,0.06)"}`,
              boxShadow: promptFocused ? "0 0 0 3px rgba(79,140,255,0.07)" : "none",
            }}
          >
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onFocus={() => setPromptFocused(true)}
              onBlur={() => setPromptFocused(false)}
              disabled={isGenerating}
              placeholder="Describe what you want to generate..."
              rows={5}
              maxLength={2000}
              className="w-full bg-transparent p-4 resize-none outline-none text-sm disabled:opacity-60 placeholder-[#374151]"
              style={{ color: "#E5E7EB", fontFamily: "'Space Grotesk', sans-serif" }}
            />
            <div
              className="flex items-center justify-end px-4 py-2.5 border-t"
              style={{ borderColor: "rgba(255,255,255,0.05)" }}
            >
              <span className="text-[10px]" style={{ color: "#374151" }}>
                {prompt.length}/2000
              </span>
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            REFERENCE IMAGES (conditional based on mode)
        ═══════════════════════════════════════════════════════════════════ */}
        
        {/* Single Reference Image (for I2V and img2img) */}
        <AnimatePresence>
          {needsReferenceImage && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <ImageUploader
                image={referenceImage}
                onUpload={onImageUpload}
                onRemove={onImageRemove}
                fileRef={fileRef}
                label="Reference Image"
                disabled={isGenerating}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* First + Last Frame (for first_last_frame mode) */}
        <AnimatePresence>
          {needsFirstLastFrames && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden space-y-4"
            >
              <ImageUploader
                image={firstFrameImage}
                onUpload={onFirstFrameUpload}
                onRemove={onFirstFrameRemove}
                fileRef={firstFrameRef}
                label="First Frame"
                disabled={isGenerating}
              />
              <ImageUploader
                image={lastFrameImage}
                onUpload={onLastFrameUpload}
                onRemove={onLastFrameRemove}
                fileRef={lastFrameRef}
                label="Last Frame"
                disabled={isGenerating}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Arbitrary Frames (for arbitrary_frame mode) */}
        <AnimatePresence>
          {needsArbitraryFrames && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <ParamLabel>Arbitrary Frames (Multi-Keyframe)</ParamLabel>
              
              {/* Existing frames */}
              <div className="space-y-3 mb-3">
                {arbitraryFrames.map((frame) => (
                  <div
                    key={frame.id}
                    className="rounded-xl p-3"
                    style={{
                      background: "rgba(79,140,255,0.04)",
                      border: "1px solid rgba(79,140,255,0.15)",
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs" style={{ color: "#6B7280" }}>
                        Frame Index:
                      </span>
                      <input
                        type="number"
                        value={frame.frameIndex}
                        onChange={(e) =>
                          onArbitraryFrameUpdate(frame.id, parseInt(e.target.value))
                        }
                        min={0}
                        max={numFrames - 1}
                        disabled={isGenerating}
                        className="flex-1 rounded-lg px-2.5 py-1.5 text-xs outline-none disabled:opacity-50"
                        style={{
                          background: "#1C212C",
                          border: "1px solid rgba(255,255,255,0.06)",
                          color: "#E5E7EB",
                        }}
                      />
                      <button
                        onClick={() => onArbitraryFrameRemove(frame.id)}
                        disabled={isGenerating}
                        className="p-1.5 rounded-lg transition-all duration-150 disabled:opacity-50"
                        style={{
                          background: "rgba(239,68,68,0.1)",
                          color: "#EF4444",
                          border: "1px solid rgba(239,68,68,0.2)",
                        }}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <img
                      src={frame.image}
                      alt={`Frame ${frame.frameIndex}`}
                      className="w-full h-24 object-cover rounded-lg"
                    />
                  </div>
                ))}
              </div>

              {/* Add new frame */}
              <div
                className="rounded-xl p-4"
                style={{
                  background: "#1C212C",
                  border: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div className="flex gap-2 mb-3">
                  <div className="flex-1">
                    <p className="text-xs mb-1.5" style={{ color: "#6B7280" }}>
                      Frame Index (0-{numFrames - 1})
                    </p>
                    <input
                      type="number"
                      value={newArbitraryFrameIndex}
                      onChange={(e) => setNewArbitraryFrameIndex(parseInt(e.target.value))}
                      min={0}
                      max={numFrames - 1}
                      disabled={isGenerating}
                      className="w-full rounded-lg px-3 py-2 text-sm outline-none disabled:opacity-50"
                      style={{
                        background: "rgba(255,255,255,0.02)",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "#E5E7EB",
                      }}
                    />
                  </div>
                </div>
                <button
                  onClick={() => arbitraryFrameRef.current?.click()}
                  disabled={isGenerating}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm transition-all duration-150 disabled:opacity-50"
                  style={{
                    background: "rgba(79,140,255,0.08)",
                    border: "1px solid rgba(79,140,255,0.2)",
                    color: "#4F8CFF",
                  }}
                >
                  <Upload className="w-4 h-4" />
                  Add Keyframe Image
                </button>
                <input
                  ref={arbitraryFrameRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      handleImageFile(file, (data) => {
                        onArbitraryFrameAdd(newArbitraryFrameIndex, data);
                        setNewArbitraryFrameIndex(Math.min(newArbitraryFrameIndex + 20, numFrames - 1));
                      });
                    }
                  }}
                  className="hidden"
                />
              </div>

              <p className="text-xs mt-2" style={{ color: "#6B7280" }}>
                💡 Add multiple reference images at different frame positions. Model will
                interpolate between them.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ═══════════════════════════════════════════════════════════════════
            ADVANCED TOGGLE
        ═══════════════════════════════════════════════════════════════════ */}
        <div className="space-y-3">
          {/* Expand/Collapse Advanced Section */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAdvanced((p) => !p)}
              className="flex-1 flex items-center gap-2 text-xs transition-colors duration-150 px-3 py-2 rounded-lg"
              style={{
                color: showAdvanced ? "#4F8CFF" : "#6B7280",
                background: showAdvanced ? "rgba(79,140,255,0.06)" : "transparent",
              }}
            >
              <Settings className="w-3.5 h-3.5" />
              Advanced settings
              {showAdvanced ? (
                <ChevronUp className="w-3.5 h-3.5 ml-auto" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 ml-auto" />
              )}
            </button>
            {/* Reset Advanced to Defaults */}
            <button
              onClick={handleResetAdvanced}
              disabled={isGenerating}
              title="Сбросить Advanced настройки по умолчанию"
              className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg transition-all duration-150 disabled:opacity-50 flex-shrink-0"
              style={{
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.07)",
                color: "#6B7280",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "rgba(79,140,255,0.35)";
                e.currentTarget.style.color = "#4F8CFF";
                e.currentTarget.style.background = "rgba(79,140,255,0.06)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)";
                e.currentTarget.style.color = "#6B7280";
                e.currentTarget.style.background = "rgba(255,255,255,0.02)";
              }}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>По умолчанию</span>
            </button>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            ADVANCED SETTINGS
        ═══════════════════════════════════════════════════════════════════ */}
        <AnimatePresence>
          {showAdvanced && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden space-y-5"
            >
              {/* Enable/Disable Advanced Settings Toggle */}
              <div
                className="rounded-xl p-3 flex items-center justify-between"
                style={{
                  background: useAdvancedSettings ? "rgba(79,140,255,0.08)" : "rgba(255,255,255,0.02)",
                  border: `1px solid ${useAdvancedSettings ? "rgba(79,140,255,0.25)" : "rgba(255,255,255,0.06)"}`,
                }}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{
                      background: useAdvancedSettings ? "rgba(79,140,255,0.15)" : "rgba(255,255,255,0.03)",
                      border: `1px solid ${useAdvancedSettings ? "rgba(79,140,255,0.3)" : "rgba(255,255,255,0.08)"}`,
                    }}
                  >
                    <Wand2 className="w-4 h-4" style={{ color: useAdvancedSettings ? "#4F8CFF" : "#6B7280" }} />
                  </div>
                  <div>
                    <p className="text-xs font-medium" style={{ color: useAdvancedSettings ? "#4F8CFF" : "#E5E7EB" }}>
                      Использовать Advanced
                    </p>
                    <p className="text-[10px]" style={{ color: "#6B7280" }}>
                      {useAdvancedSettings ? "Приоритет у точных настроек" : "Приоритет у быстрых пресетов"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setUseAdvancedSettings(!useAdvancedSettings)}
                  disabled={isGenerating}
                  className="relative w-11 h-6 rounded-full transition-all duration-200 disabled:opacity-50"
                  style={{
                    background: useAdvancedSettings ? "#4F8CFF" : "rgba(255,255,255,0.1)",
                    border: `1px solid ${useAdvancedSettings ? "#4F8CFF" : "rgba(255,255,255,0.15)"}`,
                  }}
                >
                  <div
                    className="absolute top-0.5 w-5 h-5 rounded-full transition-all duration-200"
                    style={{
                      left: useAdvancedSettings ? "calc(100% - 22px)" : "2px",
                      background: "#FFFFFF",
                      boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
                    }}
                  />
                </button>
              </div>

              {/* Priority Info Banner */}
              {!useAdvancedSettings && (
                <div
                  className="rounded-xl p-3 flex items-start gap-2"
                  style={{
                    background: "rgba(251,191,36,0.06)",
                    border: "1px solid rgba(251,191,36,0.2)",
                  }}
                >
                  <Sparkles className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "#FBD38D" }} />
                  <div>
                    <p className="text-xs font-medium mb-1" style={{ color: "#FBD38D" }}>
                      Просмотр режим
                    </p>
                    <p className="text-[10px] leading-relaxed" style={{ color: "#9CA3AF" }}>
                      Advanced настройки видны, но не используются при генерации. 
                      Приоритет у быстрых пресетов. Включите toggle выше для использования.
                    </p>
                  </div>
                </div>
              )}

              <div
                style={{
                  opacity: useAdvancedSettings ? 1 : 0.4,
                  pointerEvents: useAdvancedSettings ? "auto" : "none",
                }}
              >
                {/* Negative Prompt */}
                <div>
                  <ParamLabel>Negative Prompt</ParamLabel>
                  <textarea
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    placeholder="What to exclude..."
                    rows={2}
                    disabled={isGenerating || !useAdvancedSettings}
                    className="w-full rounded-xl px-3.5 py-3 text-sm resize-none outline-none transition-colors duration-150 placeholder-[#374151] disabled:opacity-50"
                    style={{
                      background: "#1C212C",
                      border: "1px solid rgba(255,255,255,0.06)",
                      color: "#9CA3AF",
                      fontFamily: "'Space Grotesk', sans-serif",
                    }}
                  />
                </div>

                {/* Seed */}
                <div className="mt-5">
                  <ParamLabel>Seed</ParamLabel>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={seed === -1 ? "" : seed}
                      onChange={(e) =>
                        setSeed(e.target.value === "" ? -1 : parseInt(e.target.value))
                      }
                      placeholder="Random (-1)"
                      disabled={isGenerating || !useAdvancedSettings}
                      className="flex-1 rounded-xl px-3.5 py-2.5 text-sm outline-none placeholder-[#374151] disabled:opacity-50 min-w-0"
                      style={{
                        background: "#1C212C",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "#E5E7EB",
                        fontFamily: "'Space Grotesk', sans-serif",
                      }}
                    />
                    <button
                      onClick={() => setSeed(Math.floor(Math.random() * 2147483647))}
                      disabled={isGenerating || !useAdvancedSettings}
                      className="p-2.5 rounded-xl transition-all duration-150 disabled:opacity-50"
                      style={{
                        background: "#1C212C",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "#6B7280",
                      }}
                    >
                      <Shuffle className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Width x Height */}
                <div className="mt-5">
                  <ParamLabel>Width × Height (точная настройка)</ParamLabel>
                  <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs mb-1.5" style={{ color: "#4B5563" }}>Width</p>
                    <input
                      type="number"
                      value={width}
                      onChange={(e) => setWidth(Number(e.target.value))}
                      min={256}
                      max={2048}
                      step={64}
                      disabled={isGenerating || !useAdvancedSettings}
                      className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
                      style={{
                        background: "#1C212C",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "#E5E7EB",
                        fontFamily: "'Space Grotesk', sans-serif",
                      }}
                    />
                  </div>
                  <div>
                    <p className="text-xs mb-1.5" style={{ color: "#4B5563" }}>Height</p>
                    <input
                      type="number"
                      value={height}
                      onChange={(e) => setHeight(Number(e.target.value))}
                      min={256}
                      max={2048}
                      step={64}
                      disabled={isGenerating || !useAdvancedSettings}
                      className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
                      style={{
                        background: "#1C212C",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "#E5E7EB",
                        fontFamily: "'Space Grotesk', sans-serif",
                      }}
                    />
                  </div>
                  </div>
                </div>
              </div>

              {/* ─── VIDEO-SPECIFIC ─────────────────────────────────────── */}
              {generationType === "video" && (
                <div
                  className="rounded-2xl p-4 space-y-4"
                  style={{
                    background: "rgba(79,140,255,0.03)",
                    border: "1px solid rgba(79,140,255,0.1)",
                    opacity: useAdvancedSettings ? 1 : 0.4,
                    pointerEvents: useAdvancedSettings ? "auto" : "none",
                  }}
                >
                  <p className="text-xs font-medium" style={{ color: "#4F8CFF" }}>
                    Video Parameters
                  </p>

                  {/* Num Frames */}
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>
                        Num Frames
                      </p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>
                        {numFrames} (~{(numFrames / fps).toFixed(1)}s)
                      </span>
                    </div>
                    <RangeSlider
                      min={16}
                      max={161}
                      step={1}
                      value={numFrames}
                      onChange={setNumFrames}
                      disabled={isGenerating || !useAdvancedSettings}
                    />
                  </div>

                  {/* FPS */}
                  <div>
                    <ParamLabel>FPS</ParamLabel>
                    <ToggleGroup
                      options={[
                        { value: "8", label: "8" },
                        { value: "16", label: "16" },
                        { value: "24", label: "24" },
                      ]}
                      value={String(fps)}
                      onChange={(v) => !isGenerating && !useAdvancedSettings ? null : setFps(Number(v))}
                      disabled={isGenerating || !useAdvancedSettings}
                    />
                  </div>

                  {/* Model-specific */}
                  {videoModel === "anisora" ? (
                    <div>
                      <div className="flex justify-between mb-1">
                        <p className="text-xs" style={{ color: "#6B7280" }}>
                          Motion Score
                        </p>
                        <span className="text-xs" style={{ color: "#4F8CFF" }}>
                          {motionScore.toFixed(1)}
                        </span>
                      </div>
                      <RangeSlider
                        min={0}
                        max={5}
                        step={0.1}
                        value={motionScore}
                        onChange={setMotionScore}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  ) : (
                    <div>
                      <ParamLabel>Lighting Variant</ParamLabel>
                      <ToggleGroup
                        options={[
                          { value: "low_noise", label: "Low Noise" },
                          { value: "high_noise", label: "High Noise" },
                        ]}
                        value={lightingVariant}
                        onChange={setLightingVariant}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  )}

                  {/* Reference Strength */}
                  {(videoMode === "i2v" || videoMode === "first_last_frame") && (
                    <div>
                      <div className="flex justify-between mb-1">
                        <p className="text-xs" style={{ color: "#6B7280" }}>
                          Reference Strength
                        </p>
                        <span className="text-xs" style={{ color: "#4F8CFF" }}>
                          {referenceStrength.toFixed(2)}
                        </span>
                      </div>
                      <RangeSlider
                        min={0}
                        max={1}
                        step={0.05}
                        value={referenceStrength}
                        onChange={setReferenceStrength}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  )}

                  {/* Steps & Guidance/CFG */}
                  <div>
                    <p className="text-[10px] mb-2" style={{ color: "#6B7280" }}>
                      {videoModel === "anisora" 
                        ? "⚠️ Steps: 8 (fixed), Guidance: 1.0 (optimal)"
                        : "⚠️ Steps: 4 (fixed), CFG: 1.0 (required)"}
                    </p>
                  </div>
                </div>
              )}

              {/* ─── IMAGE-SPECIFIC ─────────────────────────────────────── */}
              {generationType === "image" && (
                <div
                  className="rounded-2xl p-4 space-y-4"
                  style={{
                    background: "rgba(79,140,255,0.03)",
                    border: "1px solid rgba(79,140,255,0.1)",
                    opacity: useAdvancedSettings ? 1 : 0.4,
                    pointerEvents: useAdvancedSettings ? "auto" : "none",
                  }}
                >
                  <p className="text-xs font-medium" style={{ color: "#4F8CFF" }}>
                    Image Parameters
                  </p>

                  {/* Steps */}
                  <div>
                    <div className="flex justify-between mb-1">
                      <p className="text-xs" style={{ color: "#6B7280" }}>
                        Steps
                      </p>
                      <span className="text-xs" style={{ color: "#4F8CFF" }}>
                        {imageSteps}
                      </span>
                    </div>
                    <RangeSlider
                      min={10}
                      max={50}
                      step={1}
                      value={imageSteps}
                      onChange={setImageSteps}
                      disabled={isGenerating || !useAdvancedSettings}
                    />
                  </div>

                  {/* CFG / Guidance */}
                  {imageModel === "pony" ? (
                    <div>
                      <div className="flex justify-between mb-1">
                        <p className="text-xs" style={{ color: "#6B7280" }}>
                          CFG Scale
                        </p>
                        <span className="text-xs" style={{ color: "#4F8CFF" }}>
                          {cfgScaleImage.toFixed(1)}
                        </span>
                      </div>
                      <RangeSlider
                        min={1}
                        max={20}
                        step={0.5}
                        value={cfgScaleImage}
                        onChange={setCfgScaleImage}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  ) : (
                    <div>
                      <div className="flex justify-between mb-1">
                        <p className="text-xs" style={{ color: "#6B7280" }}>
                          Guidance Scale
                        </p>
                        <span className="text-xs" style={{ color: "#4F8CFF" }}>
                          {imageGuidanceScale.toFixed(1)}
                        </span>
                      </div>
                      <RangeSlider
                        min={1}
                        max={10}
                        step={0.5}
                        value={imageGuidanceScale}
                        onChange={setImageGuidanceScale}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  )}

                  {/* Sampler */}
                  <div>
                    <ParamLabel>Sampler</ParamLabel>
                    <select
                      value={sampler}
                      onChange={(e) => setSampler(e.target.value)}
                      disabled={isGenerating || !useAdvancedSettings}
                      className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
                      style={{
                        background: "#1C212C",
                        border: "1px solid rgba(255,255,255,0.06)",
                        color: "#E5E7EB",
                        fontFamily: "'Space Grotesk', sans-serif",
                      }}
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
                        <p className="text-xs" style={{ color: "#6B7280" }}>
                          Clip Skip
                        </p>
                        <span className="text-xs" style={{ color: "#4F8CFF" }}>
                          {clipSkip}
                        </span>
                      </div>
                      <RangeSlider
                        min={1}
                        max={4}
                        step={1}
                        value={clipSkip}
                        onChange={setClipSkip}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  )}

                  {/* Denoising (img2img) */}
                  {imageMode === "img2img" && (
                    <div>
                      <div className="flex justify-between mb-1">
                        <p className="text-xs" style={{ color: "#6B7280" }}>
                          Denoising Strength
                        </p>
                        <span className="text-xs" style={{ color: "#4F8CFF" }}>
                          {imgDenoisingStrength.toFixed(2)}
                        </span>
                      </div>
                      <RangeSlider
                        min={0}
                        max={1}
                        step={0.05}
                        value={imgDenoisingStrength}
                        onChange={setImgDenoisingStrength}
                        disabled={isGenerating || !useAdvancedSettings}
                      />
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Sticky bottom — Generate ────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 px-6 pb-6 pt-4 border-t space-y-3"
        style={{ borderColor: "rgba(255,255,255,0.06)" }}
      >
        {/* Model info */}
        <div className="flex items-center justify-between text-[11px]" style={{ color: "#4B5563" }}>
          <span>{currentModel}</span>
          <span>Est. ~{estSeconds}s</span>
        </div>

        {/* Button */}
        <button
          onClick={onGenerate}
          disabled={!canGenerate}
          className="w-full relative overflow-hidden rounded-2xl py-4 flex items-center justify-center gap-2.5 text-white text-sm transition-all duration-300 disabled:cursor-not-allowed"
          style={
            canGenerate
              ? {
                  background: "linear-gradient(135deg, #4F8CFF, #6366F1)",
                  boxShadow:
                    "0 0 28px rgba(79,140,255,0.28), 0 8px 20px rgba(0,0,0,0.3)",
                }
              : {
                  background: "#1C212C",
                  border: "1px solid rgba(255,255,255,0.06)",
                  color: "#374151",
                }
          }
          onMouseEnter={(e) => {
            if (canGenerate) {
              e.currentTarget.style.boxShadow =
                "0 0 40px rgba(79,140,255,0.4), 0 8px 24px rgba(0,0,0,0.4)";
              e.currentTarget.style.transform = "translateY(-1px)";
            }
          }}
          onMouseLeave={(e) => {
            if (canGenerate) {
              e.currentTarget.style.boxShadow =
                "0 0 28px rgba(79,140,255,0.28), 0 8px 20px rgba(0,0,0,0.3)";
              e.currentTarget.style.transform = "translateY(0)";
            }
          }}
        >
          {isGenerating ? (
            <>
              <div
                className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin"
              />
              Generating...
            </>
          ) : status === "done" ? (
            <>
              <RotateCcw className="w-4 h-4" />
              Generate Again
            </>
          ) : (
            <>
              <Wand2 className="w-4 h-4" />
              Generate {generationType === "video" ? "Video" : "Image"}
              <Sparkles className="w-3.5 h-3.5 opacity-60" />
            </>
          )}
        </button>

        {/* Hint */}
        {needsReferenceImage && !referenceImage && (
          <p className="text-xs text-center" style={{ color: "#F59E0B" }}>
            Upload a reference image to continue
          </p>
        )}
      </div>
    </div>
  );
}
