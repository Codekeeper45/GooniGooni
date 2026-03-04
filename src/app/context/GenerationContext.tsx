import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import type {
  GenerationType,
  VideoModel,
  ImageModel,
  VideoMode,
  ImageMode,
  GenerationStatus,
  ArbitraryFrameItem,
} from "../components/ControlPanel";
import type { HistoryItem } from "../components/HistoryPanel";
import { sessionFetch, ensureGenerationSession, readApiError, resolveMediaUrl } from "../utils/sessionClient";
import { configManager, type ModelId } from "../utils/configManager";
import { getPresetsForModel } from "../utils/presetManager";
import { useGallery } from "./GalleryContext";
import {
  getAvailableModes,
  getDefaultMode,
  restoreMode,
  checkEnvironmentSync,
  type GenerationModeId,
} from "../utils/environment";
import { getAPIClient, type GenerationClient, type ProgressUpdate } from "../api/apiFactory";
import { getActiveLoRAs } from "../utils/loraState";

// Status text mapping

const STAGE_LABELS: Record<string, string> = {
  queued: "Ожидание GPU воркера...",
  pending: "Ожидание GPU воркера...",
  dispatch: "Отправка на воркер...",
  model_resolve: "Загрузка модели...",
  pipeline_materialize: "Загрузка AI модели...",
  loading_model: "Загрузка AI модели...",
  preprocessing: "Подготовка входных данных...",
  generating_video: "Генерация видео...",
  generating_image: "Генерация изображения...",
  generating: "Генерация...",
  inference: "Генерация...",
  artifact_write: "Сохранение результата...",
  postprocessing: "Кодирование результата...",
  saving: "Сохранение в галерею...",
  done: "Готово!",
  failed: "Генерация не удалась",
};

function getStatusText(stage: string | null, generationType: GenerationType): string {
  if (!stage) return "Инициализация...";
  if (stage === "generating") {
    return generationType === "video" ? "Генерация видео..." : "Генерация изображения...";
  }
  return STAGE_LABELS[stage] ?? `Обработка: ${stage}`;
}

function parseEffectiveSize(stageDetail: string | null | undefined): { width: number; height: number } | null {
  if (!stageDetail || !stageDetail.startsWith("ok:")) return null;
  const match = stageDetail.match(/^ok:(\d+)x(\d+)$/);
  if (!match) return null;
  return {
    width: Number(match[1]),
    height: Number(match[2]),
  };
}

// Types

interface GenerationContextType {
  // Generation mode (local / remote)
  generationMode: GenerationModeId;
  setGenerationMode: (mode: GenerationModeId) => void;

  // Config
  generationType: GenerationType;
  setGenerationType: (t: GenerationType) => void;
  videoModel: VideoModel;
  setVideoModel: (m: VideoModel) => void;
  imageModel: ImageModel;
  setImageModel: (m: ImageModel) => void;
  videoMode: VideoMode;
  setVideoMode: (m: VideoMode) => void;
  imageMode: ImageMode;
  setImageMode: (m: ImageMode) => void;
  useAdvancedSettings: boolean;
  setUseAdvancedSettings: (u: boolean) => void;

  // Parameters
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

  // Reference Images
  referenceImage: string | null;
  setReferenceImage: (img: string | null) => void;
  firstFrameImage: string | null;
  setFirstFrameImage: (img: string | null) => void;
  lastFrameImage: string | null;
  setLastFrameImage: (img: string | null) => void;
  arbitraryFrames: ArbitraryFrameItem[];
  setArbitraryFrames: (frames: ArbitraryFrameItem[] | ((prev: ArbitraryFrameItem[]) => ArbitraryFrameItem[])) => void;

  // Video Params
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

  // Image Params
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

  // State
  status: GenerationStatus;
  progress: number;
  statusText: string;
  stageDetail: string;
  error: string | null;
  userAction: string | null;
  result: any;
  taskId: string | null;
  estSeconds: number;

  // Actions
  generate: () => Promise<void>;
  retry: () => void;
  regenerate: () => void;
  
  // History
  history: HistoryItem[];
  setHistory: (h: HistoryItem[] | ((prev: HistoryItem[]) => HistoryItem[])) => void;
}

const GenerationContext = createContext<GenerationContextType | null>(null);

// Provider

const STORAGE_KEY = "mg_generation_state_v2";
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ERRORS = 5;
const MAX_TRANSIENT_POLL_ERRORS = 12;
const WORKER_QUEUE_STALL_TIMEOUT_MS = 130_000;
const PROCESSING_STALL_TIMEOUT_MS = 300_000;
const FATAL_POLL_HTTP_CODES = new Set([401, 404, 410, 422, 500]);
const TRANSIENT_POLL_HTTP_CODES = new Set([502, 503]);

export function GenerationProvider({ children }: { children: React.ReactNode }) {
  const { addToGallery } = useGallery();

  // ── Hybrid Mode (local / remote) ───────────────────────────────────────────
  const availableModes = getAvailableModes();
  const envDefaultMode = getDefaultMode();
  const [generationMode, setGenerationModeRaw] = useState<GenerationModeId>(
    () => restoreMode(availableModes, envDefaultMode),
  );

  // Persist mode selection to sessionStorage on change
  useEffect(() => {
    try {
      sessionStorage.setItem("generation_mode", generationMode);
    } catch {
      // sessionStorage unavailable — ignore
    }
  }, [generationMode]);

  // Run environment sync check once on mount
  useEffect(() => {
    checkEnvironmentSync();
  }, []);

  // State
  const savedState = (() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed?.taskId && parsed?.result?.url) {
        parsed.result.url = resolveMediaUrl(parsed.result.url, `/results/${parsed.taskId}`);
      }
      if (parsed?.taskId && parsed?.result?.thumbnailUrl) {
        parsed.result.thumbnailUrl = resolveMediaUrl(parsed.result.thumbnailUrl, `/preview/${parsed.taskId}`);
      }
      // Revive dates in history
      if (parsed.history) {
        parsed.history = parsed.history.map((h: any) => ({
          ...h,
          createdAt: new Date(h.createdAt),
        }));
      }
      return parsed;
    } catch {
      return null;
    }
  })();

  const initialGenerationType = (savedState?.generationType ?? "video") as GenerationType;
  const initialVideoModel = (savedState?.videoModel ?? "anisora") as VideoModel;
  const initialImageModel = (savedState?.imageModel ?? "pony") as ImageModel;
  const savedWidth = typeof savedState?.width === "number" ? savedState.width : undefined;
  const savedHeight = typeof savedState?.height === "number" ? savedState.height : undefined;
  const initialImageResolution = configManager.normalizeImageResolution(
    initialImageModel,
    savedWidth ?? configManager.getPreferredInitialResolution(initialImageModel).width,
    savedHeight ?? configManager.getPreferredInitialResolution(initialImageModel).height,
  );
  const initialWidth = initialGenerationType === "image" ? initialImageResolution.width : (savedWidth ?? 720);
  const initialHeight = initialGenerationType === "image" ? initialImageResolution.height : (savedHeight ?? 1280);
  // State
  const [generationType, setGenerationType] = useState<GenerationType>(initialGenerationType);
  const [videoModel, setVideoModel] = useState<VideoModel>(initialVideoModel);
  const [imageModel, setImageModel] = useState<ImageModel>(initialImageModel);
  const [videoMode, setVideoMode] = useState<VideoMode>(savedState?.videoMode ?? "t2v");
  const [imageMode, setImageMode] = useState<ImageMode>(savedState?.imageMode ?? "txt2img");
  const [useAdvancedSettings, setUseAdvancedSettings] = useState(savedState?.useAdvancedSettings ?? false);

  const [prompt, setPrompt] = useState(savedState?.prompt ?? "");
  const [negativePrompt, setNegativePrompt] = useState(savedState?.negativePrompt ?? "");
  const [width, setWidth] = useState(initialWidth);
  const [height, setHeight] = useState(initialHeight);
  const [seed, setSeed] = useState(savedState?.seed ?? -1);
  const [outputFormat, setOutputFormat] = useState(savedState?.outputFormat ?? "mp4");

  const [referenceImage, setReferenceImage] = useState<string | null>(savedState?.referenceImage ?? null);
  const [firstFrameImage, setFirstFrameImage] = useState<string | null>(savedState?.firstFrameImage ?? null);
  const [lastFrameImage, setLastFrameImage] = useState<string | null>(savedState?.lastFrameImage ?? null);
  const [arbitraryFrames, setArbitraryFrames] = useState<ArbitraryFrameItem[]>(savedState?.arbitraryFrames ?? []);

  const [numFrames, setNumFrames] = useState(savedState?.numFrames ?? 81);
  const [videoSteps, setVideoSteps] = useState(savedState?.videoSteps ?? 8);
  const [guidanceScale, setGuidanceScale] = useState(savedState?.guidanceScale ?? 1.0);
  const [fps, setFps] = useState(savedState?.fps ?? 16);
  const [motionScore, setMotionScore] = useState(savedState?.motionScore ?? 3.0);
  const [cfgScaleVideo, setCfgScaleVideo] = useState(savedState?.cfgScaleVideo ?? 1.0);
  const [referenceStrength, setReferenceStrength] = useState(savedState?.referenceStrength ?? 0.85);
  const [lightingVariant, setLightingVariant] = useState<"high_noise" | "low_noise">(savedState?.lightingVariant ?? "low_noise");
  const [denoisingStrength, setDenoisingStrength] = useState(savedState?.denoisingStrength ?? 0.7);

  const [imageSteps, setImageSteps] = useState(savedState?.imageSteps ?? 30);
  const [cfgScaleImage, setCfgScaleImage] = useState(savedState?.cfgScaleImage ?? 6.0);
  const [clipSkip, setClipSkip] = useState(savedState?.clipSkip ?? 2);
  const [sampler, setSampler] = useState(savedState?.sampler ?? "Euler a");
  const [imageGuidanceScale, setImageGuidanceScale] = useState(savedState?.imageGuidanceScale ?? 3.5);
  const [imgDenoisingStrength, setImgDenoisingStrength] = useState(savedState?.imgDenoisingStrength ?? 0.7);

  const [status, setStatus] = useState<GenerationStatus>(savedState?.status ?? "idle");
  const [progress, setProgress] = useState(savedState?.progress ?? 0);
  const [statusText, setStatusText] = useState(savedState?.statusText ?? "");
  const [stageDetail, setStageDetail] = useState(savedState?.stageDetail ?? "");
  const [error, setError] = useState<string | null>(savedState?.error ?? null);
  const [userAction, setUserAction] = useState<string | null>(null);
  const [result, setResult] = useState<any>(savedState?.result ?? null);
  const [taskId, setTaskId] = useState<string | null>(savedState?.taskId ?? null);
  const [history, setHistory] = useState<HistoryItem[]>(savedState?.history ?? []);

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef(false);
  const localClientRef = useRef<GenerationClient | null>(null);

  // Cancellation-aware mode setter (FR-018, FR-026)
  const handleSetGenerationMode = useCallback((newMode: GenerationModeId) => {
    setGenerationModeRaw((prevMode) => {
      if (prevMode === newMode) return prevMode;

      // If there's an active generation, cancel it
      if (status === "generating") {
        // Cancel remote polling
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        abortRef.current = true;

        // Cancel local client if active
        if (prevMode === "local" && localClientRef.current) {
          localClientRef.current.cancelGeneration().catch(() => {});
        }

        // Reset generation state
        setTimeout(() => {
          setStatus("idle");
          setProgress(0);
          setStatusText("");
          setError(null);
          setStageDetail("");
          console.info(`Generation cancelled — switched to ${newMode} mode`);
        }, 0);
      }

      return newMode;
    });
  }, [status]);
  const requestSizeRef = useRef<{ width: number; height: number }>({ width: initialWidth, height: initialHeight });

  useEffect(() => {
    if (generationType !== "image") return;
    const normalized = configManager.normalizeImageResolution(imageModel, width, height);
    if (!normalized.changed) return;
    setWidth(normalized.width);
    setHeight(normalized.height);
  }, [generationType, imageModel]);

  // ── Auto-fill recommended params on image model change (US3) ───────────────
  const prevImageModelRef = useRef<ImageModel>(initialImageModel);
  useEffect(() => {
    if (generationType !== "image") return;
    if (imageModel === prevImageModelRef.current) return;
    prevImageModelRef.current = imageModel;

    const defaults = configManager.getModelDefaults(imageModel);
    if (!defaults || Object.keys(defaults).length === 0) {
      // Custom model without defaults — apply safe fallback
      setImageSteps(20);
      setCfgScaleImage(7);
      setSampler("Euler a");
      setClipSkip(2);
      setImageGuidanceScale(3.5);
      setImgDenoisingStrength(0.7);
    } else {
      if (defaults.steps !== undefined) setImageSteps(defaults.steps);
      if (defaults.cfg_scale !== undefined) setCfgScaleImage(defaults.cfg_scale);
      if (defaults.guidance_scale !== undefined) setImageGuidanceScale(defaults.guidance_scale);
      if (defaults.sampler !== undefined) setSampler(defaults.sampler);
      if (defaults.clip_skip !== undefined) setClipSkip(defaults.clip_skip);
      if (defaults.denoising_strength !== undefined) setImgDenoisingStrength(defaults.denoising_strength);
      if (defaults.width !== undefined) setWidth(defaults.width);
      if (defaults.height !== undefined) setHeight(defaults.height);
    }

    // Preset-aware override (T020): if user has a preset for this model, prefer it
    const presets = getPresetsForModel(imageModel);
    if (presets.length > 0) {
      const preset = presets[0]; // Use first (most recently saved) preset
      const p = preset.parameters;
      if (p.steps !== undefined) setImageSteps(p.steps);
      if (p.cfg_scale !== undefined) setCfgScaleImage(p.cfg_scale);
      if (p.sampler !== undefined) setSampler(p.sampler);
      if (p.clip_skip !== undefined) setClipSkip(p.clip_skip);
      if (p.width !== undefined) setWidth(p.width);
      if (p.height !== undefined) setHeight(p.height);
    }

    // Quality tags prepopulation (T018)
    const metadata = configManager.getModelMetadata(imageModel);
    if (metadata?.quality_tags) {
      const tags = metadata.quality_tags;
      setPrompt((prev: string) => {
        if (!prev.trim()) return tags + ", ";
        if (prev.includes(tags)) return prev;
        return tags + ", " + prev;
      });
    }

    // Clear negative prompt when switching to Flux (no negative prompt support)
    if (imageModel === "flux") {
      setNegativePrompt("");
    }
  }, [generationType, imageModel]);

  // Persistence Effect
  useEffect(() => {
    const state = {
      generationType, videoModel, imageModel, videoMode, imageMode, useAdvancedSettings,
      prompt, negativePrompt, width, height, seed, outputFormat,
      referenceImage, firstFrameImage, lastFrameImage, arbitraryFrames,
      numFrames, videoSteps, guidanceScale, fps, motionScore, cfgScaleVideo, referenceStrength, lightingVariant, denoisingStrength,
      imageSteps, cfgScaleImage, clipSkip, sampler, imageGuidanceScale, imgDenoisingStrength,
      status, progress, statusText, stageDetail, error, result, taskId, history
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [
    generationType, videoModel, imageModel, videoMode, imageMode, useAdvancedSettings,
    prompt, negativePrompt, width, height, seed, outputFormat,
    referenceImage, firstFrameImage, lastFrameImage, arbitraryFrames,
    numFrames, videoSteps, guidanceScale, fps, motionScore, cfgScaleVideo, referenceStrength, lightingVariant, denoisingStrength,
    imageSteps, cfgScaleImage, clipSkip, sampler, imageGuidanceScale, imgDenoisingStrength,
    status, progress, statusText, stageDetail, error, result, taskId, history
  ]);

  // Warn user before closing tab during active generation
  useEffect(() => {
    if (status !== "generating") return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [status]);

  // Derived
  const currentModelId: ModelId = generationType === "video" ? videoModel : imageModel;
  const currentMode = generationType === "video" ? videoMode : imageMode;
  const currentModelLabel = generationType === "video" 
    ? (videoModel === "anisora" ? "AniSora V3.2" : "Phr00t WAN 2.2")
    : (imageModel === "pony" ? "Pony V6 XL" : "Flux.1 dev");

  const estSeconds = configManager.calculateEstimate(currentModelId, {
    num_frames: numFrames,
    fps,
    steps: generationType === "video" ? videoSteps : imageSteps,
  });

  // Polling Logic
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const startPolling = useCallback((tid: string, resolvedSeed: number, options?: { resume?: boolean }) => {
    let consecutiveErrors = 0;
    const startedAtMs = Date.now();
    let queuedAtMs: number | null = null;
    let includeResumeFlag = options?.resume === true;
    let pollInFlight = false;
    let lastStageSignature = "";
    let lastChangeAtMs = Date.now();
    setTaskId(tid);

        const failPolling = (message: string, action?: string) => {
      stopPolling();
      setStatus("error");
      setStageDetail("failed");
      setError(message);
      setUserAction(action ?? null);
      setHistory(prev =>
        prev.map(h =>
          h.taskId === tid
            ? { ...h, status: "failed", error: message }
            : h
        ),
      );
    };

    const poll = async () => {
      if (abortRef.current || pollInFlight) return;
      pollInFlight = true;
      try {
        const statusPath = includeResumeFlag ? `/status/${tid}?resume=1` : `/status/${tid}`;
        const resp = await sessionFetch(statusPath, {}, { retryOn401: true });
        includeResumeFlag = false;
        if (!resp.ok) {
          const apiErr = await readApiError(resp, "Status check failed.");
          const message = apiErr.detail;
          const isTransient = TRANSIENT_POLL_HTTP_CODES.has(resp.status);
          if (FATAL_POLL_HTTP_CODES.has(resp.status)) {
            failPolling(message || "Generation failed.", apiErr.userAction);
            return;
          }
          if (isTransient) {
            setStatusText("Переподключение к воркеру...");
          }
          consecutiveErrors++;
          const errorBudget = isTransient ? MAX_TRANSIENT_POLL_ERRORS : MAX_POLL_ERRORS;
          if (consecutiveErrors >= errorBudget) {
            failPolling(message || "Connection to server lost.");
          }
          return;
        }

        consecutiveErrors = 0;
        const data = await resp.json();
        const currentProgress = Number(data.progress ?? 0);
        setProgress(currentProgress);
        setStatusText(getStatusText(data.stage, generationType));
        setStageDetail(typeof data.stage_detail === "string" ? data.stage_detail : "");

        // Detect processing stall — safety net for stuck tasks
        if (data.status === "processing" || (data.status === "pending" && data.stage && data.stage !== "queued")) {
          const sig = `${data.status}:${data.stage}:${data.progress}`;
          if (sig !== lastStageSignature) {
            lastStageSignature = sig;
            lastChangeAtMs = Date.now();
          } else if (Date.now() - lastChangeAtMs >= PROCESSING_STALL_TIMEOUT_MS) {
            failPolling("Генерация зависла: нет прогресса более 5 минут.");
            return;
          }
        }

        if (
          data.status === "pending" &&
          currentProgress === 0 &&
          (!data.stage || data.stage === "queued")
        ) {
          if (queuedAtMs === null) {
            const createdAtMs =
              typeof data.created_at === "string"
                ? Date.parse(data.created_at)
                : NaN;
            queuedAtMs = Number.isFinite(createdAtMs) ? createdAtMs : startedAtMs;
          }
          if (Date.now() - queuedAtMs >= WORKER_QUEUE_STALL_TIMEOUT_MS) {
            failPolling("Таймаут ожидания: GPU воркер не взял задачу вовремя.");
            return;
          }
        }

        if (data.status === "done") {
          const resultUrl = resolveMediaUrl(data.result_url, `/results/${tid}`);
          const previewUrl = data.preview_url
            ? resolveMediaUrl(data.preview_url, `/preview/${tid}`)
            : null;
          const requestedSize = requestSizeRef.current ?? { width, height };
          const finalSize = parseEffectiveSize(data.stage_detail) ?? requestedSize;

          const res = {
            url: resultUrl,
            thumbnailUrl: previewUrl || undefined,
            seed: resolvedSeed,
            width: finalSize.width,
            height: finalSize.height,
            prompt,
            model: currentModelLabel,
            type: generationType,
          };
          setResult(res);
          setStatus("done");
          setProgress(100);
          setStageDetail(typeof data.stage_detail === "string" ? data.stage_detail : "ok");
          stopPolling();

          try {
            addToGallery({
              id: tid,
              url: resultUrl,
              thumbnailUrl: previewUrl || undefined,
              prompt,
              type: generationType,
              model: currentModelLabel,
              mode: "remote",
              width: finalSize.width,
              height: finalSize.height,
              seed: resolvedSeed,
              createdAt: new Date(),
            });
          } catch (e) {
            console.error("addToGallery failed:", e);
          }

          setHistory(prev => prev.map(h => h.taskId === tid ? {
            ...h,
            status: "done",
            width: finalSize.width,
            height: finalSize.height,
            thumbnailUrl: previewUrl || resultUrl,
          } : h));
        } else if (data.status === "failed") {
          failPolling(data.error_msg ?? "Генерация не удалась.");
        }
      } catch (err: any) {
        consecutiveErrors++;
        setStatusText("Переподключение к воркеру...");
        if (consecutiveErrors >= MAX_POLL_ERRORS) {
          failPolling(err?.message || "Ошибка опроса сервера.");
        }
      } finally {
        pollInFlight = false;
      }
    };

    poll();
    pollIntervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
  }, [generationType, width, height, prompt, currentModelLabel, addToGallery, stopPolling]);

  // Resume polling on mount if taskId is set and status is generating
  useEffect(() => {
    if (status === "generating" && taskId) {
      startPolling(taskId, seed, { resume: true });
    }
    return () => {
      abortRef.current = true;
      stopPolling();
    };
  }, []); // Run once on mount

  // Actions
  const generate = useCallback(async () => {
    if (!prompt.trim() || status === "generating") return;

    setStatus("generating");
    setProgress(0);
    setStatusText("Инициализация...");
    setStageDetail("");
    setError(null);
    // Revoke old blob URL to prevent memory leak
    if (result?.url?.startsWith("blob:")) {
      URL.revokeObjectURL(result.url);
    }
    setResult(null);

    const normalizedSize = generationType === "image"
      ? configManager.normalizeImageResolution(imageModel, width, height)
      : { width, height, changed: false };
    const requestWidth = normalizedSize.width;
    const requestHeight = normalizedSize.height;
    requestSizeRef.current = { width: requestWidth, height: requestHeight };
    if (generationType === "image" && normalizedSize.changed) {
      setWidth(requestWidth);
      setHeight(requestHeight);
    }

    const resolvedSeed = seed === -1 ? Math.floor(Math.random() * 2147483647) : seed;
    const historyItem: HistoryItem = {
      id: Date.now().toString(),
      prompt,
      type: generationType,
      model: currentModelLabel,
      width: requestWidth, height: requestHeight, seed: resolvedSeed,
      createdAt: new Date(),
      status: "pending",
    };
    setHistory(prev => [historyItem, ...prev.slice(0, 49)]);

    // ── Pre-generation VRAM check (US4/T025) ──────────────────────────────────
    if (generationMode === "local") {
      try {
        const gpuResp = await fetch("/local-api/gpu");
        if (gpuResp.ok) {
          const gpuData = await gpuResp.json();
          if (gpuData.detected && gpuData.vram_free_mb != null) {
            const metadata = configManager.getModelMetadata(currentModelId);
            const requiredMb = (metadata?.vram_min_gb ?? 6) * 1024;
            if (gpuData.vram_free_mb < requiredMb) {
              const freeMb = gpuData.vram_free_mb;
              const freeGb = (freeMb / 1024).toFixed(1);
              const reqGb = (requiredMb / 1024).toFixed(0);
              const proceed = window.confirm(
                `Недостаточно VRAM для ${currentModelLabel}.\nТребуется: ${reqGb} GB, доступно: ${freeGb} GB.\nПродолжить?`
              );
              if (!proceed) {
                setStatus("idle");
                setProgress(0);
                setStatusText("");
                setHistory(prev => prev.filter(h => h.id !== historyItem.id));
                return;
              }
            }
          }
        }
      } catch {
        // GPU check failed — proceed without warning
      }
    }

    // ── Local Mode dispatch (ComfyUI) ──────────────────────────────────────
    if (generationMode === "local" && generationType === "image") {
      try {
        const client = await getAPIClient("local");

        // Wire progress updates
        client.onProgress((update: ProgressUpdate) => {
          setProgress(update.percentage);
          setStatusText(update.stage);
        });

        const localResult = await client.generate({
          model: imageModel as "pony" | "flux",
          prompt,
          negative_prompt: negativePrompt || undefined,
          width: requestWidth,
          height: requestHeight,
          seed: resolvedSeed,
          steps: imageSteps,
          cfg_scale: cfgScaleImage,
          loras: getActiveLoRAs().length > 0 ? getActiveLoRAs() : undefined,
        });

        const res = {
          url: localResult.imageData,
          seed: resolvedSeed,
          width: requestWidth,
          height: requestHeight,
          prompt,
          model: currentModelLabel,
          type: generationType,
        };
        setResult(res);
        setStatus("done");
        setProgress(100);
        setStageDetail("ok");

        try {
          addToGallery({
            id: localResult.generationId,
            url: localResult.imageData,
            prompt,
            type: generationType,
            model: currentModelLabel,
            mode: "local",
            width: requestWidth,
            height: requestHeight,
            seed: resolvedSeed,
            createdAt: new Date(),
          });
        } catch (e) {
          console.error("addToGallery failed:", e);
        }

        setHistory(prev => prev.map(h => h.id === historyItem.id ? {
          ...h,
          status: "done",
          taskId: localResult.generationId,
          thumbnailUrl: localResult.imageData,
        } : h));
      } catch (err: any) {
        setStatus("error");
        setStageDetail("failed");
        setError(err.message);
        setUserAction(err.userAction ?? null);
        setHistory(prev => prev.map(h => h.id === historyItem.id ? { ...h, status: "failed", error: err.message } : h));
      }
      return;
    }

    // ── Remote Mode dispatch (Modal backend) ───────────────────────────────
    try {
      await ensureGenerationSession();
      
      const values: any = { prompt, negative_prompt: negativePrompt, width: requestWidth, height: requestHeight, seed: resolvedSeed, output_format: outputFormat };
      if (generationType === "video") {
        Object.assign(values, { num_frames: numFrames, fps, steps: videoSteps, guidance_scale: guidanceScale, cfg_scale: cfgScaleVideo, reference_strength: referenceStrength, lighting_variant: lightingVariant, denoising_strength: denoisingStrength });
        if (videoMode === "i2v") values.reference_image = referenceImage;
        if (videoMode === "first_last_frame") { values.first_frame_image = firstFrameImage; values.last_frame_image = lastFrameImage; }
        if (videoMode === "arbitrary_frame") values.arbitrary_frames = arbitraryFrames.map(f => ({ frame_index: f.frameIndex, image: f.image, strength: referenceStrength }));
      } else {
        Object.assign(values, { steps: imageSteps, cfg_scale: cfgScaleImage, clip_skip: clipSkip, sampler, guidance_scale: imageGuidanceScale, denoising_strength: imgDenoisingStrength });
        if (imageMode === "img2img") values.reference_image = referenceImage;
      }

      const payload = configManager.buildPayload(currentModelId, currentMode, values);
      const resp = await sessionFetch("/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }, { retryOn401: true });

      if (!resp.ok) {
        const apiErr = await readApiError(resp, "Fail");
        const err = new Error(apiErr.detail);
        (err as any).userAction = apiErr.userAction;
        throw err;
      }

      const data = await resp.json();
      const tid = data.task_id;
      setTaskId(tid);
      setHistory(prev => prev.map(h => h.id === historyItem.id ? { ...h, taskId: tid } : h));
      startPolling(tid, resolvedSeed);
    } catch (err: any) {
      setStatus("error");
      setStageDetail("failed");
      setError(err.message);
      setUserAction(err.userAction ?? null);
      setHistory(prev => prev.map(h => h.id === historyItem.id ? { ...h, status: "failed", error: err.message } : h));
    }
  }, [
    prompt, status, seed, generationType, currentModelLabel, width, height, negativePrompt, outputFormat,
    numFrames, fps, videoSteps, guidanceScale, cfgScaleVideo, referenceStrength, lightingVariant, denoisingStrength,
    videoMode, referenceImage, firstFrameImage, lastFrameImage, arbitraryFrames,
    imageSteps, cfgScaleImage, clipSkip, sampler, imageGuidanceScale, imgDenoisingStrength, imageMode, imageModel,
    currentModelId, currentMode, startPolling, generationMode, addToGallery
  ]);

  const retry = useCallback(() => {
    stopPolling();
    setStatus("idle");
    setError(null);
    setUserAction(null);
  }, [stopPolling]);

  const regenerate = useCallback(() => {
    stopPolling();
    generate();
  }, [stopPolling, generate]);

  const value = {
    generationMode, setGenerationMode: handleSetGenerationMode,
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
    referenceImage, setReferenceImage,
    firstFrameImage, setFirstFrameImage,
    lastFrameImage, setLastFrameImage,
    arbitraryFrames, setArbitraryFrames,
    numFrames, setNumFrames,
    videoSteps, setVideoSteps,
    guidanceScale, setGuidanceScale,
    fps, setFps,
    motionScore, setMotionScore,
    cfgScaleVideo, setCfgScaleVideo,
    referenceStrength, setReferenceStrength,
    lightingVariant, setLightingVariant,
    denoisingStrength, setDenoisingStrength,
    imageSteps, setImageSteps,
    cfgScaleImage, setCfgScaleImage,
    clipSkip, setClipSkip,
    sampler, setSampler,
    imageGuidanceScale, setImageGuidanceScale,
    imgDenoisingStrength, setImgDenoisingStrength,
    status, progress, statusText, stageDetail, error, userAction, result, taskId, estSeconds,
    generate, retry, regenerate,
    history, setHistory
  };

  return <GenerationContext.Provider value={value}>{children}</GenerationContext.Provider>;
}

export function useGeneration() {
  const ctx = useContext(GenerationContext);
  if (!ctx) throw new Error("useGeneration must be used inside GenerationProvider");
  return ctx;
}
