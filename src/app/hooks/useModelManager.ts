/**
 * useModelManager — hook for managing ComfyUI models.
 * Talks to the Vite plugin /local-api/ endpoints.
 */

import { useState, useCallback, useEffect, useRef } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InstalledModel {
  filename: string;
  sizeBytes: number;
  sizeFormatted: string;
  modifiedAt: string;
}

export interface DownloadTask {
  id: string;
  filename: string;
  totalBytes: number;
  downloadedBytes: number;
  status: "downloading" | "complete" | "error" | "cancelled";
  error?: string;
  percentage: number;
  elapsed: number;
}

export interface CivitAIModel {
  id: number;
  name: string;
  description?: string;
  type: string;
  nsfw: boolean;
  tags: string[];
  modelVersions: CivitAIModelVersion[];
  creator?: { username: string };
  stats?: {
    downloadCount: number;
    favoriteCount: number;
    thumbsUpCount: number;
    rating: number;
    ratingCount: number;
  };
}

export interface CivitAIModelVersion {
  id: number;
  name: string;
  downloadUrl: string;
  files: Array<{
    id: number;
    name: string;
    sizeKB: number;
    type: string;
    format: string;
    downloadUrl: string;
  }>;
  images: Array<{
    url: string;
    nsfw: string;
    width: number;
    height: number;
  }>;
}

export interface RecommendedModel {
  id: string;
  name: string;
  description: string;
  filename: string;
  downloadUrl: string;
  sizeFormatted: string;
  civitaiUrl?: string;
  huggingfaceUrl?: string;
  requiredBy: string; // which workflow needs it
}

// ─── Recommended models (pre-configured) ─────────────────────────────────────

export const RECOMMENDED_MODELS: RecommendedModel[] = [
  // ── Image models ─────────────────────────────────────────────────────
  {
    id: "pony-v6",
    name: "Pony Diffusion V6 XL",
    description: "Высокое качество аниме/стилизованных изображений. Рекомендуемая модель для начала.",
    filename: "ponyDiffusionV6XL_v6StartWithThisOne.safetensors",
    downloadUrl: "https://civitai.com/api/download/models/290640",
    sizeFormatted: "~6.5 GB",
    civitaiUrl: "https://civitai.com/models/257749",
    requiredBy: "Pony V6 XL",
  },
  {
    id: "flux-dev-nf4",
    name: "Flux.1 Dev (NF4)",
    description: "Фотореалистичные изображения с точным следованием промпту. Нужно 8+ GB VRAM.",
    filename: "flux1-dev-bnb-nf4-v2.safetensors",
    downloadUrl: "https://huggingface.co/lllyasviel/flux1-dev-bnb-nf4/resolve/main/flux1-dev-bnb-nf4-v2.safetensors",
    sizeFormatted: "~12 GB",
    huggingfaceUrl: "https://huggingface.co/lllyasviel/flux1-dev-bnb-nf4",
    requiredBy: "Flux.1 dev",
  },
  // ── Video models ─────────────────────────────────────────────────────
  {
    id: "anisora-v3.2",
    name: "Index-AniSora V3.2",
    description: "Аниме-стиль видео. Генерация Text2Video / Image2Video. Модель на базе WAN 14B.",
    filename: "wan2.1-t2v-14b-anisora-v3.2.safetensors",
    downloadUrl: "https://huggingface.co/Wan-AI/Wan2.1-T2V-14B-Diffusers/resolve/main/transformer/diffusion_pytorch_model.safetensors",
    sizeFormatted: "~28 GB",
    huggingfaceUrl: "https://huggingface.co/Wan-AI/Wan2.1-T2V-14B-Diffusers",
    requiredBy: "Index-AniSora V3.2 (аниме видео)",
  },
  {
    id: "phr00t-wan2.2",
    name: "Phr00t WAN 2.2 Rapid-AllInOne",
    description: "Реалистичный стиль видео. Быстрая генерация, один файл checkpoint.",
    filename: "wan2.2-rapid-mega-aio-nsfw-v12.2.safetensors",
    downloadUrl: "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/Mega-v12/wan2.2-rapid-mega-aio-nsfw-v12.2.safetensors",
    sizeFormatted: "~28 GB",
    huggingfaceUrl: "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne",
    requiredBy: "Phr00t WAN 2.2 (реалистичное видео)",
  },
];

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useModelManager() {
  const isLocalModelManagerAvailable = import.meta.env.DEV;
  const [installedModels, setInstalledModels] = useState<InstalledModel[]>([]);
  const [downloads, setDownloads] = useState<DownloadTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [comfyStatus, setComfyStatus] = useState<{
    comfyuiFound: boolean;
    comfyuiPath: string | null;
    checkpointsDir: string | null;
    comfyuiRunning?: boolean;
  } | null>(null);

  // CivitAI search
  const [searchResults, setSearchResults] = useState<CivitAIModel[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch ComfyUI status ────────────────────────────────────────────────
  const checkStatus = useCallback(async () => {
    if (!isLocalModelManagerAvailable) {
      setComfyStatus(null);
      return;
    }
    try {
      const res = await fetch("/local-api/comfyui/status");
      const data = await res.json();
      setComfyStatus(data);
    } catch {
      setComfyStatus({ comfyuiFound: false, comfyuiPath: null, checkpointsDir: null });
    }
  }, [isLocalModelManagerAvailable]);

  // ── Refresh installed models ────────────────────────────────────────────
  const refreshModels = useCallback(async () => {
    if (!isLocalModelManagerAvailable) {
      setInstalledModels([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/local-api/models");
      const data = await res.json();
      setInstalledModels(data.models || []);
    } catch {
      setInstalledModels([]);
    } finally {
      setLoading(false);
    }
  }, [isLocalModelManagerAvailable]);

  // ── Start download ──────────────────────────────────────────────────────
  const downloadModel = useCallback(async (url: string, filename: string) => {
    try {
      const res = await fetch("/local-api/models/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, filename }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Download failed");
      // Start polling for progress
      startProgressPoll();
      return data;
    } catch (err: any) {
      throw err;
    }
  }, []);

  // ── Cancel download ─────────────────────────────────────────────────────
  const cancelDownload = useCallback(async (id: string) => {
    await fetch("/local-api/models/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
  }, []);

  // ── Delete model ────────────────────────────────────────────────────────
  const deleteModel = useCallback(async (filename: string) => {
    const res = await fetch(`/local-api/models/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || "Delete failed");
    }
    await refreshModels();
  }, [refreshModels]);

  // ── Search CivitAI ─────────────────────────────────────────────────────
  const searchCivitAI = useCallback(async (query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const res = await fetch(`/local-api/civitai/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      setSearchResults(data.items || []);
    } catch (err: any) {
      setSearchError(err.message);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  // ── Poll download progress ─────────────────────────────────────────────
  const pollProgress = useCallback(async () => {
    try {
      const res = await fetch("/local-api/models/downloads");
      const data = await res.json();
      setDownloads(data.downloads || []);

      // If all done, stop polling and refresh model list
      const active = (data.downloads || []).filter(
        (d: DownloadTask) => d.status === "downloading"
      );
      if (active.length === 0 && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        refreshModels();
      }
    } catch {}
  }, [refreshModels]);

  const startProgressPoll = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(pollProgress, 500);
  }, [pollProgress]);

  // ── Init ────────────────────────────────────────────────────────────────
  useEffect(() => {
    checkStatus();
    refreshModels();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ── Launch ComfyUI ──────────────────────────────────────────────────
  const launchComfyUI = useCallback(async () => {
    if (!isLocalModelManagerAvailable) {
      throw new Error("Local model manager is available only in development mode.");
    }
    try {
      const res = await fetch("/local-api/comfyui/launch", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to launch ComfyUI");

      // Poll status until ComfyUI is running (max 30s) without leaking timers.
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        try {
          const statusResponse = await fetch("/local-api/comfyui/status");
          const statusData = await statusResponse.json();
          if (statusData.comfyuiRunning) {
            setComfyStatus(statusData);
            return data;
          }
        } catch {
          // Keep polling until timeout; startup can be transient.
        }
      }

      await checkStatus();
      return data;
    } catch (err: any) {
      throw err;
    }
  }, [checkStatus, isLocalModelManagerAvailable]);

  // Check if a recommended model is installed
  const isModelInstalled = useCallback(
    (filename: string) => installedModels.some((m) => m.filename === filename),
    [installedModels]
  );

  return {
    // State
    installedModels,
    downloads,
    loading,
    comfyStatus,
    searchResults,
    searching,
    searchError,

    // Actions
    refreshModels,
    downloadModel,
    cancelDownload,
    deleteModel,
    searchCivitAI,
    checkStatus,
    isModelInstalled,
    launchComfyUI,

    // Constants
    recommendedModels: RECOMMENDED_MODELS,
  };
}
