import { useEffect, useRef, useState } from "react";
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

// в”Ђв”Ђв”Ђ Generation status messages в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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

// в”Ђв”Ђв”Ђ API Integration в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
type PollStatus = "pending" | "processing" | "done" | "failed";

interface PollSnapshot {
  taskId: string;
  status: PollStatus;
  progress: number;
  stage?: string;
  stageDetail?: string;
  errorMsg?: string;
  resultUrl?: string;
  previewUrl?: string;
}

interface PersistedResult {
  url: string;
  thumbnailUrl?: string;
  seed: number;
  width: number;
  height: number;
  prompt: string;
  model: string;
  type: GenerationType;
}

interface PersistedUiState {
  generationType: GenerationType;
  videoModel: VideoModel;
  imageModel: ImageModel;
  videoMode: VideoMode;
  imageMode: ImageMode;
  prompt: string;
  negativePrompt: string;
  width: number;
  height: number;
  seed: number;
  outputFormat: string;
  numFrames: number;
  videoSteps: number;
  guidanceScale: number;
  fps: number;
  motionScore: number;
  cfgScaleVideo: number;
  referenceStrength: number;
  lightingVariant: "high_noise" | "low_noise";
  denoisingStrength: number;
  imageSteps: number;
  cfgScaleImage: number;
  clipSkip: number;
  sampler: string;
  imageGuidanceScale: number;
  imgDenoisingStrength: number;
  useAdvancedSettings: boolean;
  status: GenerationStatus;
  progress: number;
  statusText: string;
  result: PersistedResult | null;
  error: string | null;
  savedAt: number;
}

const ACTIVE_TASK_KEY = "gg_active_task";
const UI_STATE_KEY = "mg_ui_state_v1";
const HISTORY_KEY = "mg_history_v1";
const MAX_HISTORY_ITEMS = 100;

interface ActiveTask {
  task_id: string;
  type: GenerationType;
  modelKey: VideoModel | ImageModel;
  mode: VideoMode | ImageMode;
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

function loadUiState(): PersistedUiState | null {
  try {
    const raw = localStorage.getItem(UI_STATE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedUiState;
  } catch {
    return null;
  }
}

function patchUiState(patch: Partial<PersistedUiState>) {
  try {
    const current = loadUiState() ?? ({} as PersistedUiState);
    const next = {
      ...current,
      ...patch,
      savedAt: Date.now(),
    };
    localStorage.setItem(UI_STATE_KEY, JSON.stringify(next));
  } catch {
    // Best-effort local persistence
  }
}

function deserializeHistory(raw: string): HistoryItem[] {
  try {
    const parsed = JSON.parse(raw) as Array<Record<string, unknown>>;
    return parsed
      .map((item) => ({
        ...(item as Omit<HistoryItem, "createdAt" | "updatedAt">),
        createdAt: new Date(String(item.createdAt ?? Date.now())),
        updatedAt: item.updatedAt ? new Date(String(item.updatedAt)) : undefined,
      }))
      .filter((item) => Boolean(item.id) && Boolean(item.prompt));
  } catch {
    return [];
  }
}

function loadHistory(): HistoryItem[] {
  const raw = localStorage.getItem(HISTORY_KEY);
  if (!raw) return [];
  return deserializeHistory(raw);
}

function saveHistory(history: HistoryItem[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY_ITEMS)));
}

async function generateMediaAPI(
  onProgress: (p: number) => void,
  onStatusText: (text: string) => void,
  params: any,
  onTaskCreated?: (task_id: string) => void,
  onTaskSnapshot?: (snapshot: PollSnapshot) => void,
): Promise<{ url: string; thumbnailUrl?: string }> {
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
      image: f.image,
    })),
  };

  const payload = configManager.buildPayload(modelId, mode, values);
  const validation = configManager.validateValues(modelId, mode, payload);
  if (!validation.valid) {
    throw new Error(`Validation failed: ${validation.errors.join(", ")}`);
  }

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
  onTaskCreated?.(task_id);
  onProgress(5);

  return pollTask(task_id, params.type, onProgress, onStatusText, onTaskSnapshot);
}

async function pollTask(
  task_id: string,
  type: GenerationType,
  onProgress: (p: number) => void,
  onStatusText: (text: string) => void,
  onTaskSnapshot?: (snapshot: PollSnapshot) => void,
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

    const normalizedStatus: PollStatus = (
      status === "done" || status === "failed" || status === "processing"
        ? status
        : "pending"
    );
    const normalizedProgress = normalizedStatus === "done" ? 100 : Math.max(5, Math.min(99, progress ?? 0));
    onProgress(normalizedProgress);
    onTaskSnapshot?.({
      taskId: task_id,
      status: normalizedStatus,
      progress: normalizedProgress,
      stage,
      stageDetail: stage_detail,
      errorMsg: error_msg,
      resultUrl: result_url,
      previewUrl: preview_url,
    });

    if (normalizedStatus === "failed") throw new Error(error_msg ?? "Generation failed on the server");

    const stageText = stage_detail || stage;
    onStatusText(stageText || (normalizedStatus === "pending" ? "Pending in queue..." : getStatusText(progress ?? 0, type)));

    if (normalizedStatus === "done") {
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

// в”Ђв”Ђв”Ђ Main Component в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
export function MediaGenApp() {
  const { addToGallery } = useGallery();
  const persistedUi = loadUiState();

  const [prompt, setPrompt] = useState<string>(() => persistedUi?.prompt ?? localStorage.getItem("mg_prompt") ?? "");

  const [generationType, setGenerationType] = useState<GenerationType>(() => persistedUi?.generationType ?? "video");
  const [videoModel, setVideoModel] = useState<VideoModel>(() => persistedUi?.videoModel ?? "anisora");
  const [imageModel, setImageModel] = useState<ImageModel>(() => persistedUi?.imageModel ?? "pony");

  const [videoMode, setVideoMode] = useState<VideoMode>(() => persistedUi?.videoMode ?? "t2v");
  const [imageMode, setImageMode] = useState<ImageMode>(() => persistedUi?.imageMode ?? "txt2img");

  const [negativePrompt, setNegativePrompt] = useState(() => persistedUi?.negativePrompt ?? "");
  const [width, setWidth] = useState(() => persistedUi?.width ?? 512);
  const [height, setHeight] = useState(() => persistedUi?.height ?? 512);
  const [seed, setSeed] = useState<number>(() => persistedUi?.seed ?? -1);
  const [outputFormat, setOutputFormat] = useState(() => persistedUi?.outputFormat ?? "mp4");

  const [referenceImage, setReferenceImage] = useState<string | null>(null);
  const [firstFrameImage, setFirstFrameImage] = useState<string | null>(null);
  const [lastFrameImage, setLastFrameImage] = useState<string | null>(null);
  const [arbitraryFrames, setArbitraryFrames] = useState<
    Array<{ id: string; frameIndex: number; image: string }>
  >([]);

  const [numFrames, setNumFrames] = useState(() => persistedUi?.numFrames ?? 81);
  const [videoSteps, setVideoSteps] = useState(() => persistedUi?.videoSteps ?? 8);
  const [guidanceScale, setGuidanceScale] = useState(() => persistedUi?.guidanceScale ?? 1.0);
  const [fps, setFps] = useState(() => persistedUi?.fps ?? 16);
  const [motionScore, setMotionScore] = useState(() => persistedUi?.motionScore ?? 3.0);
  const [cfgScaleVideo, setCfgScaleVideo] = useState(() => persistedUi?.cfgScaleVideo ?? 1.0);
  const [referenceStrength, setReferenceStrength] = useState(() => persistedUi?.referenceStrength ?? 0.85);
  const [lightingVariant, setLightingVariant] = useState<"high_noise" | "low_noise">(
    () => persistedUi?.lightingVariant ?? "low_noise"
  );
  const [denoisingStrength, setDenoisingStrength] = useState(() => persistedUi?.denoisingStrength ?? 0.7);

  const [imageSteps, setImageSteps] = useState(() => persistedUi?.imageSteps ?? 30);
  const [cfgScaleImage, setCfgScaleImage] = useState(() => persistedUi?.cfgScaleImage ?? 6);
  const [clipSkip, setClipSkip] = useState(() => persistedUi?.clipSkip ?? 2);
  const [sampler, setSampler] = useState(() => persistedUi?.sampler ?? "Euler a");
  const [imageGuidanceScale, setImageGuidanceScale] = useState(() => persistedUi?.imageGuidanceScale ?? 3.5);
  const [imgDenoisingStrength, setImgDenoisingStrength] = useState(() => persistedUi?.imgDenoisingStrength ?? 0.7);

  const [useAdvancedSettings, setUseAdvancedSettings] = useState(() => persistedUi?.useAdvancedSettings ?? false);

  const [status, setStatus] = useState<GenerationStatus>(() => persistedUi?.status ?? "idle");
  const [progress, setProgress] = useState(() => persistedUi?.progress ?? 0);
  const [statusText, setStatusText] = useState(() => persistedUi?.statusText ?? "");
  const [result, setResult] = useState<PersistedResult | null>(() => persistedUi?.result ?? null);
  const [error, setError] = useState<string | null>(() => persistedUi?.error ?? null);

  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory());
  const [showHistory, setShowHistory] = useState(false);

  const resumeStartedRef = useRef(false);
  const skipModelDefaultsRef = useRef(true);

  const anisoraFixed = configManager.getFixedParameters("anisora");
  const phr00tFixed = configManager.getFixedParameters("phr00t");
  const anisoraStepsDefault = Number(anisoraFixed.steps?.value ?? 8);
  const anisoraGuidanceDefault = Number(anisoraFixed.guidance_scale?.value ?? 1.0);
  const phr00tStepsDefault = Number(phr00tFixed.steps?.value ?? 4);
  const phr00tCfgDefault = Number(phr00tFixed.cfg_scale?.value ?? 1.0);

  const setGenerationTypePersisted = (next: GenerationType) => {
    setGenerationType(next);
    patchUiState({ generationType: next });
  };

  const setVideoModelPersisted = (next: VideoModel) => {
    setVideoModel(next);
    patchUiState({ videoModel: next });
  };

  const setImageModelPersisted = (next: ImageModel) => {
    setImageModel(next);
    patchUiState({ imageModel: next });
  };

  const setVideoModePersisted = (next: VideoMode) => {
    setVideoMode(next);
    patchUiState({ videoMode: next });
  };

  const setImageModePersisted = (next: ImageMode) => {
    setImageMode(next);
    patchUiState({ imageMode: next });
  };

  const upsertHistoryItem = (item: HistoryItem) => {
    setHistory((prev) => {
      const rest = prev.filter((h) => h.id !== item.id);
      return [item, ...rest].slice(0, MAX_HISTORY_ITEMS);
    });
  };

  const patchHistoryItem = (id: string, patch: Partial<HistoryItem>) => {
    setHistory((prev) => {
      let found = false;
      const next = prev.map((item) => {
        if (item.id !== id) return item;
        found = true;
        return { ...item, ...patch, updatedAt: new Date() };
      });
      return found ? next : prev;
    });
  };

  useEffect(() => {
    localStorage.setItem("mg_prompt", prompt);
  }, [prompt]);

  useEffect(() => {
    saveHistory(history);
  }, [history]);

  useEffect(() => {
    let cancelled = false;
    const modelLabel = (model: string): string => {
      const key = model.toLowerCase();
      if (key === "anisora") return "Index-AniSora V3.2";
      if (key === "phr00t") return "Phr00t WAN 2.2 Rapid";
      if (key === "pony") return "Pony Diffusion V6 XL";
      if (key === "flux") return "Flux.1 [dev] nf4";
      return model;
    };

    (async () => {
      try {
        await ensureGenerationSession();
        const resp = await sessionFetch(
          "/gallery?page=1&page_size=30&sort_by=created_at&sort_order=desc",
          {},
          { retryOn401: true },
        );
        if (!resp.ok) return;
        const payload = await resp.json() as {
          items: Array<{
            id: string;
            prompt: string;
            model: string;
            type: GenerationType;
            width: number;
            height: number;
            seed: number;
            created_at: string;
            preview_url?: string;
            result_url?: string;
          }>;
        };
        if (cancelled || !Array.isArray(payload.items)) return;

        setHistory((prev) => {
          const knownIds = new Set(prev.map((item) => item.id));
          const additions = payload.items
            .filter((item) => !knownIds.has(item.id))
            .map((item) => ({
              id: item.id,
              taskId: item.id,
              prompt: item.prompt,
              type: item.type,
              model: modelLabel(item.model),
              thumbnailUrl: item.preview_url || item.result_url,
              width: item.width,
              height: item.height,
              seed: item.seed,
              createdAt: new Date(item.created_at),
              updatedAt: new Date(item.created_at),
              status: "done" as const,
            }));
          if (additions.length === 0) return prev;
          return [...additions, ...prev]
            .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
            .slice(0, MAX_HISTORY_ITEMS);
        });
      } catch {
        // Best-effort history hydration from server.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const persisted: PersistedUiState = {
      generationType,
      videoModel,
      imageModel,
      videoMode,
      imageMode,
      prompt,
      negativePrompt,
      width,
      height,
      seed,
      outputFormat,
      numFrames,
      videoSteps,
      guidanceScale,
      fps,
      motionScore,
      cfgScaleVideo,
      referenceStrength,
      lightingVariant,
      denoisingStrength,
      imageSteps,
      cfgScaleImage,
      clipSkip,
      sampler,
      imageGuidanceScale,
      imgDenoisingStrength,
      useAdvancedSettings,
      status,
      progress,
      statusText,
      result,
      error,
      savedAt: Date.now(),
    };
    localStorage.setItem(UI_STATE_KEY, JSON.stringify(persisted));
  }, [
    generationType,
    videoModel,
    imageModel,
    videoMode,
    imageMode,
    prompt,
    negativePrompt,
    width,
    height,
    seed,
    outputFormat,
    numFrames,
    videoSteps,
    guidanceScale,
    fps,
    motionScore,
    cfgScaleVideo,
    referenceStrength,
    lightingVariant,
    denoisingStrength,
    imageSteps,
    cfgScaleImage,
    clipSkip,
    sampler,
    imageGuidanceScale,
    imgDenoisingStrength,
    useAdvancedSettings,
    status,
    progress,
    statusText,
    result,
    error,
  ]);

  useEffect(() => {
    if (status === "generating") {
      setStatusText(getStatusText(progress, generationType));
    }
  }, [progress, status, generationType]);

  useEffect(() => {
    if (skipModelDefaultsRef.current) {
      skipModelDefaultsRef.current = false;
      return;
    }
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

  useEffect(() => {
    if (resumeStartedRef.current) return;
    const saved = getActiveTask();
    if (!saved || !saved.task_id) return;

    resumeStartedRef.current = true;

    if (Date.now() - saved.startedAt > 25 * 60 * 1000) {
      clearActiveTask();
      return;
    }

    setGenerationTypePersisted(saved.type);
    if (saved.type === "video") {
      setVideoModelPersisted(saved.modelKey as VideoModel);
      setVideoModePersisted(saved.mode as VideoMode);
    } else {
      setImageModelPersisted(saved.modelKey as ImageModel);
      setImageModePersisted(saved.mode as ImageMode);
    }

    setStatus("generating");
    setProgress(5);
    setStatusText(getStatusText(5, saved.type));
    setError(null);
    setResult(null);

    upsertHistoryItem({
      id: saved.task_id,
      taskId: saved.task_id,
      prompt: saved.prompt,
      type: saved.type,
      model: saved.modelName,
      thumbnailUrl: undefined,
      width: saved.width,
      height: saved.height,
      seed: saved.seed,
      createdAt: new Date(saved.startedAt),
      updatedAt: new Date(),
      status: "pending",
    });

    pollTask(saved.task_id, saved.type, setProgress, setStatusText, (snapshot) => {
      patchHistoryItem(saved.task_id, {
        status: snapshot.status === "processing" ? "pending" : snapshot.status,
        error: snapshot.status === "failed" ? snapshot.errorMsg : undefined,
        thumbnailUrl: snapshot.previewUrl,
      });
    })
      .then(({ url: resultUrl, thumbnailUrl }) => {
        const newResult = {
          url: resultUrl,
          thumbnailUrl,
          seed: saved.seed,
          width: saved.width,
          height: saved.height,
          prompt: saved.prompt,
          model: saved.modelName,
          type: saved.type,
        };
        setResult(newResult);
        setStatus("done");
        setProgress(100);
        clearActiveTask();

        patchHistoryItem(saved.task_id, {
          status: "done",
          thumbnailUrl: thumbnailUrl || resultUrl,
          error: undefined,
        });

        const galleryItem: GalleryItem = {
          id: saved.task_id,
          url: resultUrl,
          thumbnailUrl,
          prompt: saved.prompt,
          type: saved.type,
          model: saved.modelName,
          width: saved.width,
          height: saved.height,
          seed: saved.seed,
          createdAt: new Date(saved.startedAt),
        };
        addToGallery(galleryItem);
      })
      .catch((err) => {
        clearActiveTask();
        setStatus("error");
        const message = err instanceof Error ? err.message : "Generation failed";
        setError(message);
        patchHistoryItem(saved.task_id, { status: "failed", error: message });
      });
  }, [addToGallery]);

  const estSeconds = calcEstSeconds(
    generationType,
    generationType === "video" ? numFrames : undefined,
    generationType === "image" ? imageSteps : undefined
  );

  const handleGenerate = async () => {
    if (!prompt.trim()) return;

    if (generationType === "video") {
      if (videoMode === "i2v" && !referenceImage) {
        return;
      }
      if (videoMode === "first_last_frame" && (!firstFrameImage || !lastFrameImage)) {
        return;
      }
    } else if (imageMode === "img2img" && !referenceImage) {
      return;
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
    let capturedTaskId = "";

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
        (task_id) => {
          capturedTaskId = task_id;
          const pendingTask: ActiveTask = {
            task_id,
            type: generationType,
            modelKey: generationType === "video" ? videoModel : imageModel,
            mode: generationType === "video" ? videoMode : imageMode,
            prompt,
            modelName,
            width,
            height,
            seed: resolvedSeed,
            startedAt: Date.now(),
          };
          saveActiveTask(pendingTask);
          upsertHistoryItem({
            id: task_id,
            taskId: task_id,
            prompt,
            type: generationType,
            model: modelName,
            thumbnailUrl: undefined,
            width,
            height,
            seed: resolvedSeed,
            createdAt: new Date(),
            updatedAt: new Date(),
            status: "pending",
          });
        },
        (snapshot) => {
          patchHistoryItem(snapshot.taskId, {
            status: snapshot.status === "processing" ? "pending" : snapshot.status,
            error: snapshot.status === "failed" ? snapshot.errorMsg : undefined,
            thumbnailUrl: snapshot.previewUrl,
          });
        }
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

      const itemId = capturedTaskId || Date.now().toString();
      patchHistoryItem(itemId, {
        status: "done",
        thumbnailUrl: thumbnailUrl || resultUrl,
        error: undefined,
      });
      if (!capturedTaskId) {
        upsertHistoryItem({
          id: itemId,
          taskId: itemId,
          prompt,
          type: generationType,
          model: modelName,
          thumbnailUrl: thumbnailUrl || resultUrl,
          width,
          height,
          seed: resolvedSeed,
          createdAt: new Date(),
          updatedAt: new Date(),
          status: "done",
        });
      }

      const galleryItem: GalleryItem = {
        id: itemId,
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
      const message = err instanceof Error ? err.message : "Connection to inference server failed.";
      setError(message);
      if (capturedTaskId) {
        patchHistoryItem(capturedTaskId, { status: "failed", error: message });
      }
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
    setGenerationTypePersisted(item.type);
    if (item.type === "video") {
      if (item.model.toLowerCase().includes("phr00t")) {
        setVideoModelPersisted("phr00t");
      } else {
        setVideoModelPersisted("anisora");
      }
    } else {
      if (item.model.toLowerCase().includes("flux")) {
        setImageModelPersisted("flux");
      } else {
        setImageModelPersisted("pony");
      }
    }
    setWidth(item.width);
    setHeight(item.height);
    setShowHistory(false);
  };

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

  const handleVideoModeChange = (mode: VideoMode) => {
    setVideoModePersisted(mode);
    setReferenceImage(null);
    setFirstFrameImage(null);
    setLastFrameImage(null);
    setArbitraryFrames([]);
  };

  const handleImageModeChange = (mode: ImageMode) => {
    setImageModePersisted(mode);
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
      {/* в”Ђв”Ђ Navbar в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ */}
      <Navbar
        onHistoryClick={() => setShowHistory(true)}
        historyCount={history.length}
      />

      {/* в”Ђв”Ђ Main layout в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: Control Panel */}
        <ControlPanel
          // Type & Model
          generationType={generationType}
          setGenerationType={setGenerationTypePersisted}
          videoModel={videoModel}
          setVideoModel={setVideoModelPersisted}
          imageModel={imageModel}
          setImageModel={setImageModelPersisted}
          
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
        onClear={() => {
          setHistory([]);
          saveHistory([]);
        }}
      />
    </div>
  );
}


