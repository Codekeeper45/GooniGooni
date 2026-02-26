import { useState, useEffect } from "react";
import { Navbar } from "./Navbar";
import { ControlPanel } from "./ControlPanel";
import { OutputPanel } from "./OutputPanel";
import { HistoryPanel } from "./HistoryPanel";
import { useGallery } from "../context/GalleryContext";
import type { GalleryItem } from "../context/GalleryContext";
import type { 
  GenerationType, 
  VideoModel, 
  ImageModel,
  VideoMode,
  ImageMode,
  GenerationStatus 
} from "./ControlPanel";
import type { HistoryItem } from "./HistoryPanel";

const API_URL = ((import.meta as any).env.VITE_API_URL as string | undefined) ?? "";

// ─── Generation status messages ───────────────────────────────────────────────

function getStatusText(progress: number, type: GenerationType): string {
  if (type === "video") {
    if (progress < 8) return "Initializing video model...";
    if (progress < 20) return "Encoding prompt...";
    if (progress < 45) return "Rendering frames...";
    if (progress < 75) return "Upscaling...";
    if (progress < 92) return "Applying enhancements...";
    return "Finalizing video...";
  } else {
    if (progress < 15) return "Loading image model...";
    if (progress < 35) return "Processing prompt...";
    if (progress < 70) return "Generating image...";
    if (progress < 92) return "Refining details...";
    return "Finalizing...";
  }
}

import { configManager } from "../utils/configManager";
import type { ModelId } from "../utils/configManager";
import { ensureGenerationSession, readApiError, sessionFetch } from "../utils/sessionClient";

// ─── API Integration ─────────────────────────────────────────────────────────
async function generateMediaAPI(
  onProgress: (p: number) => void,
  onStatusText: (text: string) => void,
  params: any,
  onTaskCreated?: (task_id: string) => void
): Promise<{ url: string; thumbnailUrl?: string }> {
  // Build structured payload via configManager
  const modelId: ModelId = params.type === "video" ? params.videoModel : params.imageModel;
  const mode = params.type === "video" ? params.videoMode : params.imageMode;

  const values = {
    ...params,
    num_frames: params.numFrames,
    steps: params.type === "video" ? params.videoSteps : params.imageSteps,
    cfg_scale: params.type === "video" ? params.cfgScaleVideo : params.cfgScaleImage,
    guidance_scale: params.type === "video" ? params.guidanceScale : params.imageGuidanceScale,
    output_format: params.outputFormat,
    reference_image: params.referenceImage,
    init_image: params.referenceImage,
    first_frame_image: params.firstFrameImage,
    last_frame_image: params.lastFrameImage,
    arbitrary_frames: params.arbitraryFrames.map((f: any) => ({
      frame_index: f.frameIndex,
      image: f.image
    }))
  };

  const payload = configManager.buildPayload(modelId, mode, values);
  const validation = configManager.validateValues(modelId, mode, payload);
  if (!validation.valid) {
    throw new Error(`Validation failed: ${validation.errors.join(", ")}`);
  }

  console.log("🚀 Payload for inference:", payload);
  console.log("📋 Advanced settings:", params.useAdvancedSettings ? "ON" : "OFF");

  if (!API_URL) {
    throw new Error("Backend not configured. Set VITE_API_URL in .env and rebuild the app.");
  }

  await ensureGenerationSession();
  const genRes = await sessionFetch(
    "/generate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    { retryOn401: true }
  );

  if (!genRes.ok) {
    const err = await readApiError(genRes, "Generate request failed.");
    const detail = err.detail;
    const code = err.code;
    const userAction = err.userAction;
    if (genRes.status === 503 && code === "queue_overloaded") {
      throw new Error("Queue overloaded: all safe video workers are busy. Retry in 30s.");
    }
    if (genRes.status === 422) {
      throw new Error(`Validation error: ${detail} ${userAction}`.trim());
    }
    throw new Error(`Generate failed (${genRes.status}): ${detail} ${userAction}`.trim());
  }

  const { task_id } = await genRes.json() as { task_id: string };
  console.log(`📦 Task created: ${task_id}`);
  onTaskCreated?.(task_id);
  onProgress(5);

  return pollTask(task_id, params.type, onProgress, onStatusText);
}

// ─── Active task persistence helpers ─────────────────────────────────────────
const ACTIVE_TASK_KEY = "gg_active_task";

interface ActiveTask {
  task_id: string;
  type: string;
  prompt: string;
  modelName: string;
  width: number;
  height: number;
  seed: number;
  startedAt: number;
}

function saveActiveTask(t: ActiveTask) {
  localStorage.setItem(ACTIVE_TASK_KEY, JSON.stringify(t));
}
function clearActiveTask() {
  localStorage.removeItem(ACTIVE_TASK_KEY);
}
function getActiveTask(): ActiveTask | null {
  try {
    const raw = localStorage.getItem(ACTIVE_TASK_KEY);
    return raw ? (JSON.parse(raw) as ActiveTask) : null;
  } catch {
    return null;
  }
}

/** Poll task until done/failed — reusable for both new and resumed tasks. */
async function pollTask(
  task_id: string,
  type: GenerationType,
  onProgress: (p: number) => void,
  onStatusText: (text: string) => void
): Promise<{ url: string; thumbnailUrl?: string }> {
  const POLL_INTERVAL_MS = 3000;
  const MAX_POLLS = 400;

  for (let poll = 0; poll < MAX_POLLS; poll++) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    const statusRes = await sessionFetch(`/status/${task_id}`, {}, { retryOn401: true });
    if (!statusRes.ok) {
      const err = await readApiError(statusRes, "Status check failed.");
      throw new Error(`Status check failed (${statusRes.status}): ${err.detail} ${err.userAction}`.trim());
    }
    const { status, progress, error_msg, stage, stage_detail, result_url, preview_url } = await statusRes.json() as {
      status: string;
      progress: number;
      error_msg?: string;
      stage?: string;
      stage_detail?: string;
      result_url?: string;
      preview_url?: string;
    };
    onProgress(status === "done" ? 100 : Math.max(5, Math.min(99, progress ?? 0)));
    
    if (status === "failed") throw new Error(error_msg ?? "Generation failed on the server");
    
    const stageText = stage_detail || stage;
    onStatusText(stageText || (status === "pending" ? "Pending in queue..." : getStatusText(progress ?? 0, type)));

    if (status === "done") {
      const resultUrl = result_url || `${API_URL}/results/${task_id}`;
      const previewUrl = preview_url || `${API_URL}/preview/${task_id}`;
      return { url: resultUrl, thumbnailUrl: type === "video" ? previewUrl : undefined };
    }
  }
  throw new Error("Generation timed out after polling limit reached");
}


function calcEstSeconds(
  type: GenerationType,
  videoFrames?: number,
  imageSteps?: number
): number {
  if (type === "video") {
    // num_frames / fps * complexity_factor
    const frames = videoFrames || 81;
    return Math.round((frames / 16) * 3.5);
  } else {
    // steps * step_time
    const steps = imageSteps || 30;
    return Math.round(steps * 0.4);
  }
}

// ─── Main Component ────────────────────────────────────────────────────────────
export function MediaGenApp() {
  const { addToGallery } = useGallery();

  // ── Persisted state ─────────────────────────────────────────────────────────
  const [prompt, setPromptRaw] = useState<string>(
    () => localStorage.getItem("mg_prompt") ?? ""
  );
  const setPrompt = (p: string) => {
    setPromptRaw(p);
    localStorage.setItem("mg_prompt", p);
  };

  // ── Type & Model selection ───────────────────────────────────────────────────
  const [generationType, setGenerationType] = useState<GenerationType>("video");
  const [videoModel, setVideoModel] = useState<VideoModel>("anisora");
  const [imageModel, setImageModel] = useState<ImageModel>("pony");

  // ── Mode selection ───────────────────────────────────────────────────────────
  const [videoMode, setVideoMode] = useState<VideoMode>("t2v");
  const [imageMode, setImageMode] = useState<ImageMode>("txt2img");

  // ── Common parameters ─────────────────────────────────────────────────────────
  const [negativePrompt, setNegativePrompt] = useState("");
  const [width, setWidth] = useState(512);
  const [height, setHeight] = useState(512);
  const [seed, setSeed] = useState<number>(-1);
  const [batchSize, setBatchSize] = useState(1);
  const [outputFormat, setOutputFormat] = useState("mp4");

  // ── Reference images (multiple modes) ─────────────────────────────────────────
  const [referenceImage, setReferenceImage] = useState<string | null>(null);
  const [firstFrameImage, setFirstFrameImage] = useState<string | null>(null);
  const [lastFrameImage, setLastFrameImage] = useState<string | null>(null);
  const [arbitraryFrames, setArbitraryFrames] = useState<
    Array<{ id: string; frameIndex: number; image: string }>
  >([]);

  // ── Video-specific parameters ─────────────────────────────────────────────────
  const [numFrames, setNumFrames] = useState(81);
  const [videoSteps, setVideoSteps] = useState(8);
  const [guidanceScale, setGuidanceScale] = useState(1.0);
  const [fps, setFps] = useState(16);
  const [motionScore, setMotionScore] = useState(3.0);
  const [cfgScaleVideo, setCfgScaleVideo] = useState(1.0);
  const [referenceStrength, setReferenceStrength] = useState(0.85);
  const [lightingVariant, setLightingVariant] = useState<"high_noise" | "low_noise">("low_noise");
  const [denoisingStrength, setDenoisingStrength] = useState(0.7);

  // ── Image-specific parameters ─────────────────────────────────────────────────
  const [imageSteps, setImageSteps] = useState(30);
  const [cfgScaleImage, setCfgScaleImage] = useState(6);
  const [clipSkip, setClipSkip] = useState(2);
  const [sampler, setSampler] = useState("Euler a");
  const [imageGuidanceScale, setImageGuidanceScale] = useState(3.5);
  const [imgDenoisingStrength, setImgDenoisingStrength] = useState(0.7);

  // ── Advanced settings control ────────────────────────────────────────────────
  const [useAdvancedSettings, setUseAdvancedSettings] = useState(false);

  // ── Generation state ──────────────────────────────────────────────────────────
  const [status, setStatus] = useState<GenerationStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
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
  const [error, setError] = useState<string | null>(null);

  // ── History & Gallery ─────────────────────────────────────────────────────────
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const anisoraFixed = configManager.getFixedParameters("anisora");
  const phr00tFixed = configManager.getFixedParameters("phr00t");
  const anisoraStepsDefault = Number(anisoraFixed.steps?.value ?? 8);
  const anisoraGuidanceDefault = Number(anisoraFixed.guidance_scale?.value ?? 1.0);
  const phr00tStepsDefault = Number(phr00tFixed.steps?.value ?? 4);
  const phr00tCfgDefault = Number(phr00tFixed.cfg_scale?.value ?? 1.0);

  // Update status text as progress changes
  useEffect(() => {
    if (status === "generating") {
      setStatusText(getStatusText(progress, generationType));
    }
  }, [progress, status, generationType]);

  // Auto-update defaults when model changes
  useEffect(() => {
    if (generationType === "video") {
      if (videoModel === "anisora") {
        setVideoSteps(anisoraStepsDefault);
        setGuidanceScale(anisoraGuidanceDefault);
        setFps(16);
        setMotionScore(3.0);
      } else if (videoModel === "phr00t") {
        setVideoSteps(phr00tStepsDefault);
        setCfgScaleVideo(phr00tCfgDefault);
        setFps(16);
      }
    } else {
      if (imageModel === "pony") {
        setImageSteps(30);
        setCfgScaleImage(6);
        setClipSkip(2);
        setSampler("Euler a");
      } else if (imageModel === "flux") {
        setImageSteps(25);
        setImageGuidanceScale(3.5);
        setSampler("Euler");
      }
    }
  }, [
    generationType,
    videoModel,
    imageModel,
    anisoraStepsDefault,
    anisoraGuidanceDefault,
    phr00tStepsDefault,
    phr00tCfgDefault,
  ]);

  // ── Resume generation from localStorage on page load ─────────────────────────
  useEffect(() => {
    const saved = getActiveTask();
    if (!saved || !saved.task_id) return;

    // Only resume if task started less than 25 minutes ago to avoid stale tasks
    if (Date.now() - saved.startedAt > 25 * 60 * 1000) {
      clearActiveTask();
      return;
    }

    setStatus("generating");
    setProgress(5);
    setStatusText(getStatusText(5, saved.type as GenerationType));
    setError(null);
    setResult(null);

    pollTask(saved.task_id, saved.type as GenerationType, setProgress, setStatusText)
      .then(({ url: resultUrl, thumbnailUrl }) => {
        const newResult = {
          url: resultUrl,
          thumbnailUrl,
          seed: saved.seed,
          width: saved.width,
          height: saved.height,
          prompt: saved.prompt,
          model: saved.modelName,
          type: saved.type as GenerationType,
        };
        setResult(newResult);
        setStatus("done");
        setProgress(100);
        clearActiveTask();
      })
      .catch((err) => {
        clearActiveTask();
        setStatus("error");
        setError(err instanceof Error ? err.message : "Generation failed");
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const estSeconds = calcEstSeconds(
    generationType,
    generationType === "video" ? numFrames : undefined,
    generationType === "image" ? imageSteps : undefined
  );

  // ── Generate ──────────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    
    if (generationType === "video") {
      if (videoMode === "i2v" && !referenceImage) {
        return;
      }
      if (videoMode === "first_last_frame" && (!firstFrameImage || !lastFrameImage)) {
        return;
      }
    } else {
      if (imageMode === "img2img" && !referenceImage) {
        return;
      }
    }
    
    if (status === "generating") return;

    const finalSeed = useAdvancedSettings ? seed : -1;
    const finalNegativePrompt = useAdvancedSettings ? negativePrompt : "";
    
    const resolvedSeed = finalSeed === -1 ? Math.floor(Math.random() * 2147483647) : finalSeed;

    setStatus("generating");
    setProgress(0);
    setStatusText(getStatusText(0, generationType));
    setError(null);
    setResult(null);

    try {
      const modelName =
        generationType === "video"
          ? videoModel === "anisora"
            ? "Index-AniSora V3.2"
            : "Phr00t WAN 2.2 Rapid"
          : imageModel === "pony"
            ? "Pony Diffusion V6 XL"
            : "Flux.1 [dev] nf4";

      clearActiveTask();
      const { url: resultUrl, thumbnailUrl } = await generateMediaAPI(
        (p) => setProgress(p),
        (text) => setStatusText(text),
        {
          type: generationType,
          useAdvancedSettings,
          prompt,
          negativePrompt: finalNegativePrompt,
          width,
          height,
          seed: resolvedSeed,
          outputFormat,
          videoModel,
          videoMode,
          numFrames,
          videoSteps,
          fps,
          guidanceScale,
          cfgScaleVideo,
          motionScore,
          lightingVariant,
          denoisingStrength,
          referenceImage,
          referenceStrength,
          firstFrameImage,
          lastFrameImage,
          arbitraryFrames,
          imageModel,
          imageMode,
          imageSteps,
          cfgScaleImage,
          imageGuidanceScale,
          clipSkip,
          sampler,
          imgDenoisingStrength,
        },
        // Save real task_id as soon as server assigns it
        (task_id) => saveActiveTask({
          task_id,
          type: generationType,
          prompt,
          modelName,
          width,
          height,
          seed: resolvedSeed,
          startedAt: Date.now(),
        })
      );

      clearActiveTask();
      const newResult = {
        url: resultUrl,
        thumbnailUrl,
        seed: resolvedSeed,
        width,
        height,
        prompt,
        model: modelName,
        type: generationType,
      };

      setResult(newResult);
      setStatus("done");
      setProgress(100);

      // Add to history
      const historyItem: HistoryItem = {
        id: Date.now().toString(),
        prompt,
        type: generationType,
        model: modelName,
        thumbnailUrl: thumbnailUrl || resultUrl,
        width,
        height,
        seed: resolvedSeed,
        createdAt: new Date(),
      };
      setHistory((prev) => [historyItem, ...prev.slice(0, 49)]);

      // Add to gallery via context
      const galleryItem: GalleryItem = {
        id: Date.now().toString(),
        url: resultUrl,
        thumbnailUrl,
        prompt,
        type: generationType,
        model: modelName,
        width,
        height,
        seed: resolvedSeed,
        createdAt: new Date(),
      };
      addToGallery(galleryItem);
    } catch (err) {
      clearActiveTask();
      setStatus("error");
      setError(err instanceof Error ? err.message : "Connection to inference server failed.");
    }
  };

  const handleRetry = () => {
    setStatus("idle");
    setError(null);
  };

  const handleRegenerate = () => {
    handleGenerate();
  };

  const handleReuseHistory = (item: HistoryItem) => {
    setPrompt(item.prompt);
    setGenerationType(item.type);
    setWidth(item.width);
    setHeight(item.height);
    setShowHistory(false);
  };

  // ── Handlers for multiple frames ──────────────────────────────────────────────
  const handleArbitraryFrameAdd = (frameIndex: number, image: string) => {
    setArbitraryFrames((prev) => [
      ...prev,
      { id: Date.now().toString(), frameIndex, image },
    ]);
  };

  const handleArbitraryFrameRemove = (id: string) => {
    setArbitraryFrames((prev) => prev.filter((f) => f.id !== id));
  };

  const handleArbitraryFrameUpdate = (id: string, frameIndex: number) => {
    setArbitraryFrames((prev) =>
      prev.map((f) => (f.id === id ? { ...f, frameIndex } : f))
    );
  };

  // Clear frames when mode changes
  const handleVideoModeChange = (mode: VideoMode) => {
    setVideoMode(mode);
    // Clear all reference images
    setReferenceImage(null);
    setFirstFrameImage(null);
    setLastFrameImage(null);
    setArbitraryFrames([]);
  };

  const handleImageModeChange = (mode: ImageMode) => {
    setImageMode(mode);
    setReferenceImage(null);
  };

  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{
        background: "#0F1117",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#E5E7EB",
      }}
    >
      {/* ── Navbar ─────────────────────────────────────────────────────────── */}
      <Navbar
        onHistoryClick={() => setShowHistory(true)}
        historyCount={history.length}
      />

      {/* ── Main layout ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: Control Panel */}
        <ControlPanel
          // Type & Model
          generationType={generationType}
          setGenerationType={setGenerationType}
          videoModel={videoModel}
          setVideoModel={setVideoModel}
          imageModel={imageModel}
          setImageModel={setImageModel}
          
          // Mode
          videoMode={videoMode}
          setVideoMode={handleVideoModeChange}
          imageMode={imageMode}
          setImageMode={handleImageModeChange}
          
          // Advanced Settings Control
          useAdvancedSettings={useAdvancedSettings}
          setUseAdvancedSettings={setUseAdvancedSettings}
          
          // Common params
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
          batchSize={batchSize}
          setBatchSize={setBatchSize}
          outputFormat={outputFormat}
          setOutputFormat={setOutputFormat}
          
          // Reference images
          referenceImage={referenceImage}
          onImageUpload={(data) => setReferenceImage(data)}
          onImageRemove={() => setReferenceImage(null)}
          firstFrameImage={firstFrameImage}
          lastFrameImage={lastFrameImage}
          onFirstFrameUpload={(data) => setFirstFrameImage(data)}
          onLastFrameUpload={(data) => setLastFrameImage(data)}
          onFirstFrameRemove={() => setFirstFrameImage(null)}
          onLastFrameRemove={() => setLastFrameImage(null)}
          arbitraryFrames={arbitraryFrames}
          onArbitraryFrameAdd={handleArbitraryFrameAdd}
          onArbitraryFrameRemove={handleArbitraryFrameRemove}
          onArbitraryFrameUpdate={handleArbitraryFrameUpdate}
          
          // Video params
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
          
          // Image params
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
          
          // Actions
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
          mode={generationType === "video" ? videoMode : imageMode}
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
