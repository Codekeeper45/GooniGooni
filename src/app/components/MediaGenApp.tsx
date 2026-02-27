/**
 * MediaGenApp — E2E Generation Orchestrator
 * ==========================================
 * Root component that wires ControlPanel → Backend API → OutputPanel → Gallery.
 *
 * Flow:
 *   1. User configures params in ControlPanel
 *   2. handleGenerate() → POST /generate → {task_id}
 *   3. Poll GET /status/{task_id} every 2s → progress/stage updates
 *   4. On done → GET /results/{task_id} → blob URL
 *   5. Save to GalleryContext + local history
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { Navbar } from "./Navbar";
import { ControlPanel } from "./ControlPanel";
import { OutputPanel } from "./OutputPanel";
import { HistoryPanel } from "./HistoryPanel";
import type {
  GenerationType,
  VideoModel,
  ImageModel,
  VideoMode,
  ImageMode,
  GenerationStatus,
  ArbitraryFrameItem,
} from "./ControlPanel";
import type { HistoryItem } from "./HistoryPanel";
import { useGallery } from "../context/GalleryContext";
import {
  sessionFetch,
  ensureGenerationSession,
  readApiError,
} from "../utils/sessionClient";
import { configManager } from "../utils/configManager";
import type { ModelId } from "../utils/configManager";

// ─── Status text mapping ──────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting for GPU worker…",
  pending: "Waiting for GPU worker…",
  loading_model: "Loading AI model…",
  preprocessing: "Preparing inputs…",
  generating_video: "Generating video…",
  generating_image: "Generating image…",
  generating: "Generating…",
  postprocessing: "Encoding result…",
  saving: "Saving to gallery…",
  done: "Complete!",
  failed: "Generation failed",
};

function getStatusText(stage: string | null, generationType: GenerationType): string {
  if (!stage) return "Initializing…";
  if (stage === "generating") {
    return generationType === "video" ? "Generating video…" : "Generating image…";
  }
  return STAGE_LABELS[stage] ?? `Processing: ${stage}`;
}

// ─── Polling interval ─────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ERRORS = 5;
const HISTORY_STORAGE_KEY = "gg_history_v1";
const ACTIVE_TASK_STORAGE_KEY = "gg_active_task_v1";

type ActiveTaskSnapshot = {
  taskId: string;
  type: GenerationType;
  prompt: string;
  model: string;
  width: number;
  height: number;
  seed: number;
  startedAt: number;
};

function saveHistory(items: HistoryItem[]) {
  if (typeof window === "undefined") return;
  const payload = items.map((item) => ({
    ...item,
    createdAt: item.createdAt instanceof Date ? item.createdAt.toISOString() : item.createdAt,
    updatedAt: item.updatedAt instanceof Date ? item.updatedAt.toISOString() : item.updatedAt,
  }));
  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(payload));
}

function loadHistory(): HistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => ({
        ...item,
        createdAt: new Date(item.createdAt),
        updatedAt: item.updatedAt ? new Date(item.updatedAt) : undefined,
      }))
      .filter((item) => item.id && item.prompt && item.type);
  } catch {
    return [];
  }
}

function saveActiveTask(task: ActiveTaskSnapshot) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTIVE_TASK_STORAGE_KEY, JSON.stringify(task));
}

function loadActiveTask(): ActiveTaskSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.taskId || !parsed?.type) return null;
    return parsed;
  } catch {
    return null;
  }
}

function clearActiveTask() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
}

// ─── Component ────────────────────────────────────────────────────────────────

export function MediaGenApp() {
  const { addToGallery } = useGallery();

  // ── Generation type & model ─────────────────────────────────────────────────
  const [generationType, setGenerationType] = useState<GenerationType>("video");
  const [videoModel, setVideoModel] = useState<VideoModel>("anisora");
  const [imageModel, setImageModel] = useState<ImageModel>("pony");

  // ── Mode ────────────────────────────────────────────────────────────────────
  const [videoMode, setVideoMode] = useState<VideoMode>("t2v");
  const [imageMode, setImageMode] = useState<ImageMode>("txt2img");

  // ── Advanced settings toggle ────────────────────────────────────────────────
  const [useAdvancedSettings, setUseAdvancedSettings] = useState(false);

  // ── Common params ───────────────────────────────────────────────────────────
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [width, setWidth] = useState(720);
  const [height, setHeight] = useState(1280);
  const [seed, setSeed] = useState(-1);
  const [outputFormat, setOutputFormat] = useState("mp4");

  // ── Reference images (single) ───────────────────────────────────────────────
  const [referenceImage, setReferenceImage] = useState<string | null>(null);

  // ── Multi-frame references ──────────────────────────────────────────────────
  const [firstFrameImage, setFirstFrameImage] = useState<string | null>(null);
  const [lastFrameImage, setLastFrameImage] = useState<string | null>(null);

  // ── Arbitrary frames ────────────────────────────────────────────────────────
  const [arbitraryFrames, setArbitraryFrames] = useState<ArbitraryFrameItem[]>([]);

  // ── Video params ────────────────────────────────────────────────────────────
  const [numFrames, setNumFrames] = useState(81);
  const [videoSteps, setVideoSteps] = useState(8);
  const [guidanceScale, setGuidanceScale] = useState(1.0);
  const [fps, setFps] = useState(16);
  const [motionScore, setMotionScore] = useState(3.0);
  const [cfgScaleVideo, setCfgScaleVideo] = useState(1.0);
  const [referenceStrength, setReferenceStrength] = useState(0.85);
  const [lightingVariant, setLightingVariant] = useState<"high_noise" | "low_noise">("low_noise");
  const [denoisingStrength, setDenoisingStrength] = useState(0.7);

  // ── Image params ────────────────────────────────────────────────────────────
  const [imageSteps, setImageSteps] = useState(30);
  const [cfgScaleImage, setCfgScaleImage] = useState(6.0);
  const [clipSkip, setClipSkip] = useState(2);
  const [sampler, setSampler] = useState("Euler a");
  const [imageGuidanceScale, setImageGuidanceScale] = useState(3.5);
  const [imgDenoisingStrength, setImgDenoisingStrength] = useState(0.7);

  // ── Generation state ────────────────────────────────────────────────────────
  const [status, setStatus] = useState<GenerationStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    url: string;
    thumbnailUrl?: string;
    seed: number;
    width: number;
    height: number;
    prompt: string;
    model: string;
    type: GenerationType;
  } | null>(null);

  // ── History ─────────────────────────────────────────────────────────────────
  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory());
  const [showHistory, setShowHistory] = useState(false);
  const resumedRef = useRef(false);

  // ── Refs for cleanup ────────────────────────────────────────────────────────
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef(false);

  // ── Cleanup on unmount ──────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      abortRef.current = true;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  useEffect(() => {
    saveHistory(history);
  }, [history]);

  // ── Derived model ID for configManager ──────────────────────────────────────
  const currentModelId: ModelId =
    generationType === "video" ? videoModel : imageModel;
  const currentMode =
    generationType === "video" ? videoMode : imageMode;
  const currentModelLabel =
    generationType === "video"
      ? videoModel === "anisora"
        ? "AniSora V3.2"
        : "Phr00t WAN 2.2"
      : imageModel === "pony"
        ? "Pony V6 XL"
        : "Flux.1 dev";

  const estSeconds = configManager.calculateEstimate(currentModelId, {
    num_frames: numFrames,
    fps,
    steps: generationType === "video" ? videoSteps : imageSteps,
  });

  // ── Build API payload from current state ────────────────────────────────────
  const buildCurrentPayload = useCallback(() => {
    const values: Record<string, any> = {
      prompt,
      negative_prompt: negativePrompt,
      width,
      height,
      seed,
      output_format: outputFormat,
    };

    if (generationType === "video") {
      values.num_frames = numFrames;
      values.fps = fps;
      values.steps = videoSteps;
      values.guidance_scale = guidanceScale;
      values.cfg_scale = cfgScaleVideo;
      values.reference_strength = referenceStrength;
      values.lighting_variant = lightingVariant;
      values.denoising_strength = denoisingStrength;

      if (videoMode === "i2v" && referenceImage) {
        values.reference_image = referenceImage;
      }
      if (videoMode === "first_last_frame") {
        values.first_frame_image = firstFrameImage;
        values.last_frame_image = lastFrameImage;
      }
      if (videoMode === "arbitrary_frame" && arbitraryFrames.length > 0) {
        values.arbitrary_frames = arbitraryFrames.map((f) => ({
          frame_index: f.frameIndex,
          image: f.image,
          strength: referenceStrength,
        }));
      }
    } else {
      values.steps = imageSteps;
      values.cfg_scale = cfgScaleImage;
      values.clip_skip = clipSkip;
      values.sampler = sampler;
      values.guidance_scale = imageGuidanceScale;
      values.denoising_strength = imgDenoisingStrength;

      if (imageMode === "img2img" && referenceImage) {
        values.reference_image = referenceImage;
      }
    }

    return configManager.buildPayload(currentModelId, currentMode, values);
  }, [
    prompt, negativePrompt, width, height, seed, outputFormat,
    generationType, currentModelId, currentMode,
    numFrames, fps, videoSteps, guidanceScale, cfgScaleVideo,
    referenceStrength, lightingVariant, denoisingStrength,
    videoMode, referenceImage, firstFrameImage, lastFrameImage,
    arbitraryFrames,
    imageSteps, cfgScaleImage, clipSkip, sampler, imageGuidanceScale,
    imgDenoisingStrength, imageMode,
  ]);

  // ── Poll status loop ────────────────────────────────────────────────────────
  const startPolling = useCallback(
    (
      taskId: string,
      resolvedSeed: number,
      taskContext?: {
        type: GenerationType;
        prompt: string;
        model: string;
        width: number;
        height: number;
      },
    ) => {
      abortRef.current = false;
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }

      const context = taskContext ?? {
        type: generationType,
        prompt,
        model: currentModelLabel,
        width,
        height,
      };
      let consecutiveErrors = 0;

      const poll = async () => {
        if (abortRef.current) return;
        try {
          const resp = await sessionFetch(`/status/${taskId}`, {}, { retryOn401: true });
          if (!resp.ok) {
            const err = await readApiError(resp, "Status check failed");
            consecutiveErrors++;
            if (consecutiveErrors >= MAX_POLL_ERRORS) {
              stopPolling();
              setStatus("error");
              setError(err.detail);
            }
            return;
          }

          consecutiveErrors = 0;
          const data = await resp.json();

          // Update progress & stage
          setProgress(data.progress ?? 0);
          setStatusText(getStatusText(data.stage, context.type));

          if (data.status === "done") {
            stopPolling();
            clearActiveTask();

            // Build result URL — use result_url from status if available,
            // otherwise construct from /results/{task_id}
            const API_URL = ((import.meta as any).env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
            const resultUrl = data.result_url ?? `${API_URL}/results/${taskId}`;
            const previewUrl = data.preview_url;

            setResult({
              url: resultUrl,
              thumbnailUrl: previewUrl ?? undefined,
              seed: resolvedSeed,
              width: context.width,
              height: context.height,
              prompt: context.prompt,
              model: context.model,
              type: context.type,
            });
            setStatus("done");
            setProgress(100);

            // Save to gallery
            addToGallery({
              id: taskId,
              url: resultUrl,
              thumbnailUrl: previewUrl ?? undefined,
              prompt: context.prompt,
              type: context.type,
              model: context.model,
              width: context.width,
              height: context.height,
              seed: resolvedSeed,
              createdAt: new Date(),
            });

            // Update history item status
            setHistory((prev) =>
              prev.map((h) =>
                h.taskId === taskId ? { ...h, status: "done" as const, thumbnailUrl: previewUrl ?? resultUrl } : h
              )
            );
          } else if (data.status === "failed") {
            stopPolling();
            clearActiveTask();
            setStatus("error");
            setError(data.error_msg ?? "Generation failed on the server.");

            // Update history item status
            setHistory((prev) =>
              prev.map((h) =>
                h.taskId === taskId
                  ? { ...h, status: "failed" as const, error: data.error_msg ?? "Failed" }
                  : h
              )
            );
          }
        } catch (err) {
          consecutiveErrors++;
          if (consecutiveErrors >= MAX_POLL_ERRORS) {
            stopPolling();
            setStatus("error");
            setError("Connection to server lost. Please retry.");
          }
        }
      };

      // First poll immediately
      poll();
      pollIntervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    },
    [generationType, width, height, prompt, currentModelLabel, addToGallery]
  );

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // ── Generate handler ────────────────────────────────────────────────────────
  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) return;
    if (status === "generating") return;

    abortRef.current = false;
    setStatus("generating");
    setProgress(0);
    setStatusText("Initializing…");
    setError(null);
    setResult(null);

    const resolvedSeed = seed === -1 ? Math.floor(Math.random() * 2147483647) : seed;

    // Add to history immediately as "pending"
    const historyItem: HistoryItem = {
      id: Date.now().toString(),
      prompt,
      type: generationType,
      model: currentModelLabel,
      width,
      height,
      seed: resolvedSeed,
      createdAt: new Date(),
      status: "pending",
    };
    setHistory((prev) => [historyItem, ...prev.slice(0, 49)]);

    try {
      // 1. Ensure session
      await ensureGenerationSession();

      // 2. Build payload
      const payload = buildCurrentPayload();
      // Override seed with resolved value
      payload.seed = resolvedSeed;

      // 3. POST /generate
      const resp = await sessionFetch(
        "/generate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        { retryOn401: true }
      );

      if (!resp.ok) {
        const apiErr = await readApiError(resp, "Generation request failed");
        throw new Error(`${apiErr.detail} ${apiErr.userAction}`.trim());
      }

      const data = await resp.json();
      const taskId = data.task_id as string;
      saveActiveTask({
        taskId,
        type: generationType,
        prompt,
        model: currentModelLabel,
        width,
        height,
        seed: resolvedSeed,
        startedAt: Date.now(),
      });

      // Update history item with task ID
      setHistory((prev) =>
        prev.map((h) => (h.id === historyItem.id ? { ...h, taskId } : h))
      );

      // 4. Start polling
      startPolling(taskId, resolvedSeed);
    } catch (err: any) {
      setStatus("error");
      setError(err?.message ?? "Failed to start generation.");

      // Update history item as failed
      setHistory((prev) =>
        prev.map((h) =>
          h.id === historyItem.id
            ? { ...h, status: "failed" as const, error: err?.message }
            : h
        )
      );
      clearActiveTask();
    }
  }, [
    prompt, status, seed, generationType, currentModelLabel,
    width, height, buildCurrentPayload, startPolling,
  ]);

  useEffect(() => {
    if (resumedRef.current) return;
    const saved = loadActiveTask();
    if (!saved) return;
    resumedRef.current = true;
    setStatus("generating");
    setProgress(0);
    setStatusText("Resuming active task...");
    setHistory((prev) => {
      if (prev.some((item) => item.taskId === saved.taskId || item.id === saved.taskId)) {
        return prev;
      }
      const restored: HistoryItem = {
        id: saved.taskId,
        taskId: saved.taskId,
        prompt: saved.prompt,
        type: saved.type,
        model: saved.model,
        width: saved.width,
        height: saved.height,
        seed: saved.seed,
        createdAt: new Date(saved.startedAt),
        status: "pending",
      };
      return [restored, ...prev.slice(0, 49)];
    });
    startPolling(saved.taskId, saved.seed, {
      type: saved.type,
      prompt: saved.prompt,
      model: saved.model,
      width: saved.width,
      height: saved.height,
    });
  }, [startPolling]);

  // ── Retry / Regenerate handlers ─────────────────────────────────────────────
  const handleRetry = useCallback(() => {
    stopPolling();
    setStatus("idle");
    setError(null);
  }, [stopPolling]);

  const handleRegenerate = useCallback(() => {
    stopPolling();
    handleGenerate();
  }, [stopPolling, handleGenerate]);

  // ── History reuse ───────────────────────────────────────────────────────────
  const handleReuseHistory = useCallback((item: HistoryItem) => {
    setPrompt(item.prompt);
    if (item.type) {
      setGenerationType(item.type);
    }
    setShowHistory(false);
  }, []);

  // ── Arbitrary frame handlers ────────────────────────────────────────────────
  const handleArbitraryFrameAdd = useCallback((frameIndex: number, image: string) => {
    setArbitraryFrames((prev) => [
      ...prev,
      { id: Date.now().toString(), frameIndex, image },
    ]);
  }, []);

  const handleArbitraryFrameRemove = useCallback((id: string) => {
    setArbitraryFrames((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const handleArbitraryFrameUpdate = useCallback((id: string, frameIndex: number) => {
    setArbitraryFrames((prev) =>
      prev.map((f) => (f.id === id ? { ...f, frameIndex } : f))
    );
  }, []);

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{
        background: "#0F1117",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#E5E7EB",
      }}
    >
      {/* Navbar */}
      <Navbar
        onHistoryClick={() => setShowHistory(true)}
        historyCount={history.length}
      />

      {/* Main layout */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: Control Panel */}
        <ControlPanel
          generationType={generationType}
          setGenerationType={setGenerationType}
          videoModel={videoModel}
          setVideoModel={setVideoModel}
          imageModel={imageModel}
          setImageModel={setImageModel}
          videoMode={videoMode}
          setVideoMode={setVideoMode}
          imageMode={imageMode}
          setImageMode={setImageMode}
          useAdvancedSettings={useAdvancedSettings}
          setUseAdvancedSettings={setUseAdvancedSettings}
          prompt={prompt}
          setPrompt={setPrompt}
          negativePrompt={negativePrompt}
          setNegativePrompt={setNegativePrompt}
          width={width}
          setWidth={setWidth}
          height={height}
          setHeight={setHeight}
          seed={seed}
          setSeed={setSeed}
          outputFormat={outputFormat}
          setOutputFormat={setOutputFormat}
          referenceImage={referenceImage}
          onImageUpload={setReferenceImage}
          onImageRemove={() => setReferenceImage(null)}
          firstFrameImage={firstFrameImage}
          lastFrameImage={lastFrameImage}
          onFirstFrameUpload={setFirstFrameImage}
          onLastFrameUpload={setLastFrameImage}
          onFirstFrameRemove={() => setFirstFrameImage(null)}
          onLastFrameRemove={() => setLastFrameImage(null)}
          arbitraryFrames={arbitraryFrames}
          onArbitraryFrameAdd={handleArbitraryFrameAdd}
          onArbitraryFrameRemove={handleArbitraryFrameRemove}
          onArbitraryFrameUpdate={handleArbitraryFrameUpdate}
          numFrames={numFrames}
          setNumFrames={setNumFrames}
          videoSteps={videoSteps}
          setVideoSteps={setVideoSteps}
          guidanceScale={guidanceScale}
          setGuidanceScale={setGuidanceScale}
          fps={fps}
          setFps={setFps}
          motionScore={motionScore}
          setMotionScore={setMotionScore}
          cfgScaleVideo={cfgScaleVideo}
          setCfgScaleVideo={setCfgScaleVideo}
          referenceStrength={referenceStrength}
          setReferenceStrength={setReferenceStrength}
          lightingVariant={lightingVariant}
          setLightingVariant={setLightingVariant}
          denoisingStrength={denoisingStrength}
          setDenoisingStrength={setDenoisingStrength}
          imageSteps={imageSteps}
          setImageSteps={setImageSteps}
          cfgScaleImage={cfgScaleImage}
          setCfgScaleImage={setCfgScaleImage}
          clipSkip={clipSkip}
          setClipSkip={setClipSkip}
          sampler={sampler}
          setSampler={setSampler}
          imageGuidanceScale={imageGuidanceScale}
          setImageGuidanceScale={setImageGuidanceScale}
          imgDenoisingStrength={imgDenoisingStrength}
          setImgDenoisingStrength={setImgDenoisingStrength}
          onGenerate={handleGenerate}
          status={status}
          estSeconds={estSeconds}
        />

        {/* Right: Output Panel */}
        <OutputPanel
          status={status}
          progress={progress}
          statusText={statusText}
          result={result}
          error={error}
          referenceImage={referenceImage}
          generationType={generationType}
          mode={currentMode}
          onRetry={handleRetry}
          onRegenerate={handleRegenerate}
          estSeconds={estSeconds}
        />
      </div>

      {/* History side panel */}
      <HistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        history={history}
        onReuse={handleReuseHistory}
        onClear={() => setHistory([])}
      />
    </div>
  );
}
