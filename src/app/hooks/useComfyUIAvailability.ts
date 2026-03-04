/**
 * Hook: poll ComfyUI /system_stats at a configurable interval.
 * Returns live connection status for local-mode UI indicators.
 *
 * @module useComfyUIAvailability
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { configManager } from "../utils/configManager";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

export type ComfyUIStatus = "connected" | "disconnected" | "checking";

export interface ComfyUIAvailability {
  /** Live connection status */
  status: ComfyUIStatus;
  /** Last successful check timestamp (ms epoch), or null if never connected */
  lastCheckTime: number | null;
  /** Run a manual check right now */
  checkNow: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

const COMFY_STATS_URL = "/comfy-api/system_stats";

// ═══════════════════════════════════════════════════════════════════════════════
// Hook
// ═══════════════════════════════════════════════════════════════════════════════

export function useComfyUIAvailability(enabled = true): ComfyUIAvailability {
  const [status, setStatus] = useState<ComfyUIStatus>("checking");
  const [lastCheckTime, setLastCheckTime] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const runCheck = useCallback(async () => {
    if (!enabled) {
      setStatus("disconnected");
      return;
    }

    setStatus("checking");

    try {
      const resp = await fetch(COMFY_STATS_URL, { signal: AbortSignal.timeout(5000) });
      if (resp.ok) {
        setStatus("connected");
        setLastCheckTime(Date.now());
      } else {
        setStatus("disconnected");
      }
    } catch {
      setStatus("disconnected");
    }
  }, [enabled]);

  // Start / stop polling
  useEffect(() => {
    if (!enabled) {
      setStatus("disconnected");
      return;
    }

    // Initial check
    runCheck();

    const intervalMs =
      configManager.getLocalModeConfig().health_check_interval_ms ?? 10_000;

    timerRef.current = setInterval(runCheck, intervalMs);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [enabled, runCheck]);

  return { status, lastCheckTime, checkNow: runCheck };
}
