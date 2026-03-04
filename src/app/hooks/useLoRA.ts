/**
 * useLoRA — Manages LoRA file state, selection (max 5), and strength controls.
 * Fetches from /local-api/loras on mount. Supports compatibility filtering.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { configManager, type ModelId } from "../utils/configManager";

export interface LoRAFile {
  filename: string;
  path: string;
  compatible_base: "sdxl" | "flux" | "unknown";
  size_mb: number;
}

export interface LoRASelection {
  path: string;
  filename: string;
  strength_model: number;
  strength_clip: number;
}

const MAX_LORAS = 5;

interface UseLoRAResult {
  /** All available LoRA files (already filtered by compatibility) */
  files: LoRAFile[];
  /** All scanned files (unfiltered) */
  allFiles: LoRAFile[];
  /** Currently selected LoRAs with strength settings */
  selected: LoRASelection[];
  loading: boolean;
  error: string | null;
  /** Scan path where LoRAs are found */
  scanPath: string | null;
  /** Whether the section should be visible (image model with lora_base) */
  visible: boolean;
  toggleLoRA: (path: string) => void;
  setStrength: (path: string, field: "strength_model" | "strength_clip", value: number) => void;
  refresh: () => void;
}

export function useLoRA(currentModelId: ModelId | null): UseLoRAResult {
  const [allFiles, setAllFiles] = useState<LoRAFile[]>([]);
  const [selected, setSelected] = useState<LoRASelection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanPath, setScanPath] = useState<string | null>(null);

  const metadata = currentModelId ? configManager.getModelMetadata(currentModelId) : null;
  const loraBase = metadata?.lora_base ?? null;
  const visible = loraBase !== null;

  const fetchLoRAs = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const endpoint = refresh ? "/local-api/loras/refresh" : "/local-api/loras";
      const method = refresh ? "POST" : "GET";
      const resp = await fetch(endpoint, { method });
      if (!resp.ok) throw new Error(`LoRA endpoint returned ${resp.status}`);
      const data = await resp.json();
      setAllFiles(data.loras ?? []);
      setScanPath(data.scan_path ?? null);
    } catch (err: any) {
      setError(err.message || "Не удалось загрузить LoRA");
      setAllFiles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLoRAs();
  }, [fetchLoRAs]);

  // Filter files by compatibility with current model
  const files = useMemo(() => {
    if (!loraBase) return [];
    return allFiles.filter(
      (f) => f.compatible_base === loraBase || f.compatible_base === "unknown"
    );
  }, [allFiles, loraBase]);

  // Clear incompatible selections when model changes
  useEffect(() => {
    if (!loraBase) {
      setSelected([]);
      return;
    }
    setSelected((prev) =>
      prev.filter((s) => {
        const file = allFiles.find((f) => f.path === s.path);
        return file && (file.compatible_base === loraBase || file.compatible_base === "unknown");
      })
    );
  }, [loraBase, allFiles]);

  const toggleLoRA = useCallback((loraPath: string) => {
    setSelected((prev) => {
      const existing = prev.find((s) => s.path === loraPath);
      if (existing) {
        return prev.filter((s) => s.path !== loraPath);
      }
      if (prev.length >= MAX_LORAS) {
        return prev; // Max reached — silently ignore
      }
      const file = allFiles.find((f) => f.path === loraPath);
      if (!file) return prev;
      return [...prev, {
        path: loraPath,
        filename: file.filename,
        strength_model: 1.0,
        strength_clip: 1.0,
      }];
    });
  }, [allFiles]);

  const setStrength = useCallback((loraPath: string, field: "strength_model" | "strength_clip", value: number) => {
    setSelected((prev) =>
      prev.map((s) => s.path === loraPath ? { ...s, [field]: value } : s)
    );
  }, []);

  const refresh = useCallback(() => {
    fetchLoRAs(true);
  }, [fetchLoRAs]);

  return {
    files,
    allFiles,
    selected,
    loading,
    error,
    scanPath,
    visible,
    toggleLoRA,
    setStrength,
    refresh,
  };
}
