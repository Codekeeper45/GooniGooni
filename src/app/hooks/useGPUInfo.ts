/**
 * useGPUInfo — Fetches GPU info from /local-api/gpu on mount,
 * caches result in state, exposes refresh.
 */

import { useState, useEffect, useCallback } from "react";

export interface GPUInfo {
  detected: boolean;
  name: string | null;
  vram_total_mb: number | null;
  vram_free_mb: number | null;
  driver_version: string | null;
  cuda_version: string | null;
  vram_level: "green" | "yellow" | "orange" | "red";
}

interface UseGPUInfoResult {
  gpuInfo: GPUInfo | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useGPUInfo(): UseGPUInfoResult {
  const [gpuInfo, setGpuInfo] = useState<GPUInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGPU = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/local-api/gpu");
      if (!resp.ok) {
        throw new Error(`GPU endpoint returned ${resp.status}`);
      }
      const data: GPUInfo = await resp.json();
      setGpuInfo(data);
    } catch (err: any) {
      setError(err.message || "Не удалось получить информацию о GPU");
      setGpuInfo(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGPU();
  }, [fetchGPU]);

  return { gpuInfo, loading, error, refresh: fetchGPU };
}
