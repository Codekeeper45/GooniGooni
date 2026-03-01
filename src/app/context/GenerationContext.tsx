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
import { useGallery } from "./GalleryContext";

// Status text mapping

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting for GPU worker...",
  pending: "Waiting for GPU worker...",
  dispatch: "Dispatching to worker...",
  model_resolve: "Resolving model...",
  pipeline_materialize: "Loading AI model...",
  loading_model: "Loading AI model...",
  preprocessing: "Preparing inputs...",
  generating_video: "Generating video...",
  generating_image: "Generating image...",
  generating: "Generating...",
  inference: "Generating...",
  artifact_write: "Saving result...",
  postprocessing: "Encoding result...",
  saving: "Saving to gallery...",
  done: "Complete!",
  failed: "Generation failed",
};

function getStatusText(stage: string | null, generationType: GenerationType): string {
  if (!stage) return "Initializing...";
  if (stage === "generating") {
    return generationType === "video" ? "Generating video..." : "Generating image...";
  }
  return STAGE_LABELS[stage] ?? `Processing: ${stage}`;
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
const WORKER_QUEUE_STALL_TIMEOUT_MS = 130_000;
const FATAL_POLL_HTTP_CODES = new Set([401, 404, 410, 422, 500, 502, 503]);

export function GenerationProvider({ children }: { children: React.ReactNode }) {
  const { addToGallery } = useGallery();

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
  const [result, setResult] = useState<any>(savedState?.result ?? null);
  const [taskId, setTaskId] = useState<string | null>(savedState?.taskId ?? null);
  const [history, setHistory] = useState<HistoryItem[]>(savedState?.history ?? []);

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef(false);
  const requestSizeRef = useRef<{ width: number; height: number }>({ width: initialWidth, height: initialHeight });

  useEffect(() => {
    if (generationType !== "image") return;
    const normalized = configManager.normalizeImageResolution(imageModel, width, height);
    if (!normalized.changed) return;
    setWidth(normalized.width);
    setHeight(normalized.height);
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
    setTaskId(tid);

        const failPolling = (message: string) => {
      stopPolling();
      setStatus("error");
      setStageDetail("failed");
      setError(message);
      setHistory(prev =>
        prev.map(h =>
          h.taskId === tid
            ? { ...h, status: "failed", error: message }
            : h
        ),
      );
    };

    const poll = async () => {
      if (abortRef.current) return;
      try {
        const statusPath = includeResumeFlag ? `/status/${tid}?resume=1` : `/status/${tid}`;
        const resp = await sessionFetch(statusPath, {}, { retryOn401: true });
        includeResumeFlag = false;
        if (!resp.ok) {
          const apiErr = await readApiError(resp, "Status check failed.");
          const message = `${apiErr.detail} ${apiErr.userAction}`.trim();
          if (FATAL_POLL_HTTP_CODES.has(resp.status)) {
            failPolling(message || "Generation failed.");
            return;
          }
          consecutiveErrors++;
          if (consecutiveErrors >= MAX_POLL_ERRORS) {
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
            failPolling("Worker start timeout: no GPU worker picked up the task in time.");
            return;
          }
        }

        if (data.status === "done") {
          stopPolling();
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

          addToGallery({
            id: tid,
            url: resultUrl,
            thumbnailUrl: previewUrl || undefined,
            prompt,
            type: generationType,
            model: currentModelLabel,
            width: finalSize.width,
            height: finalSize.height,
            seed: resolvedSeed,
            createdAt: new Date(),
          });

          setHistory(prev => prev.map(h => h.taskId === tid ? {
            ...h,
            status: "done",
            width: finalSize.width,
            height: finalSize.height,
            thumbnailUrl: previewUrl || resultUrl,
          } : h));
        } else if (data.status === "failed") {
          failPolling(data.error_msg ?? "Generation failed.");
        }
      } catch (err: any) {
        consecutiveErrors++;
        if (consecutiveErrors >= MAX_POLL_ERRORS) {
          failPolling(err?.message || "Polling error.");
        }
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
    setStatusText("Initializing...");
    setStageDetail("");
    setError(null);
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
        throw new Error(`${apiErr.detail} ${apiErr.userAction}`.trim());
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
      setHistory(prev => prev.map(h => h.id === historyItem.id ? { ...h, status: "failed", error: err.message } : h));
    }
  }, [
    prompt, status, seed, generationType, currentModelLabel, width, height, negativePrompt, outputFormat,
    numFrames, fps, videoSteps, guidanceScale, cfgScaleVideo, referenceStrength, lightingVariant, denoisingStrength,
    videoMode, referenceImage, firstFrameImage, lastFrameImage, arbitraryFrames,
    imageSteps, cfgScaleImage, clipSkip, sampler, imageGuidanceScale, imgDenoisingStrength, imageMode, imageModel,
    currentModelId, currentMode, startPolling
  ]);

  const retry = useCallback(() => {
    stopPolling();
    setStatus("idle");
    setError(null);
  }, [stopPolling]);

  const regenerate = useCallback(() => {
    stopPolling();
    generate();
  }, [stopPolling, generate]);

  const value = {
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
    status, progress, statusText, stageDetail, error, result, taskId, estSeconds,
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
