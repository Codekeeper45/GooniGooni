/**
 * Environment detector module.
 * Reads VITE_ENVIRONMENT to determine runtime context and available generation modes.
 * @module environment
 */

import inferenceSettings from "../../inference_settings.json";
import { sessionFetch, readApiError } from "./sessionClient";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

export type EnvironmentType = "local" | "production";
export type GenerationModeId = "local" | "remote";

export interface EnvironmentConfig {
  environment: EnvironmentType;
  isLocalModeAvailable: boolean;
  isRemoteModeAvailable: boolean;
  comfyuiUrl: string | null;
  backendUrl: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Singleton
// ═══════════════════════════════════════════════════════════════════════════════

let _cachedConfig: Readonly<EnvironmentConfig> | null = null;

// ═══════════════════════════════════════════════════════════════════════════════
// Core functions
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Detect the current environment from VITE_ENVIRONMENT.
 * Defaults to "local" when the variable is unset.
 * Throws on invalid values (FR-005: fail fast).
 */
export function detectEnvironment(): Readonly<EnvironmentConfig> {
  if (_cachedConfig) return _cachedConfig;

  const settings = inferenceSettings as any;
  const rawEnv = (import.meta.env.VITE_ENVIRONMENT as string | undefined) ?? "";
  const envValue = rawEnv.trim().toLowerCase();

  // Determine environment type
  let environment: EnvironmentType;
  const validOptions: string[] = settings.environment?.options ?? ["local", "production"];

  if (!envValue || envValue === "") {
    // Default to local when not set (FR-004)
    environment = (settings.environment?.default as EnvironmentType) ?? "local";
  } else if (validOptions.includes(envValue)) {
    environment = envValue as EnvironmentType;
  } else {
    // FR-005: fail fast on invalid
    throw new Error(
      `[Environment] Invalid VITE_ENVIRONMENT value: "${rawEnv}". ` +
      `Valid values: ${validOptions.join(", ")}. ` +
      `Unset the variable to default to "${settings.environment?.default ?? "local"}".`
    );
  }

  // Derive available modes from settings
  const availableModes: GenerationModeId[] =
    (settings.available_modes?.[environment] as GenerationModeId[]) ?? ["remote"];
  const defaultMode: GenerationModeId =
    (settings.default_mode?.[environment] as GenerationModeId) ?? "remote";

  const config: EnvironmentConfig = {
    environment,
    isLocalModeAvailable: availableModes.includes("local"),
    isRemoteModeAvailable: availableModes.includes("remote"),
    comfyuiUrl: environment === "local"
      ? (settings.local_mode?.comfyui_url ?? "http://127.0.0.1:8188")
      : null,
    backendUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? "",
  };

  // Freeze to prevent console-based override (FR-015)
  _cachedConfig = Object.freeze(config);

  console.log(
    `[Environment] Detected: ${environment} | Modes: ${availableModes.join(", ")} | Default: ${defaultMode}`
  );

  return _cachedConfig;
}

/**
 * Returns true if Local Mode is available in the current environment.
 * In production, always returns false regardless of any override attempt.
 */
export function isLocalModeAvailable(): boolean {
  const config = detectEnvironment();
  return config.isLocalModeAvailable;
}

/**
 * Returns true if Remote Mode is available (always true).
 */
export function isRemoteModeAvailable(): boolean {
  return true;
}

/**
 * Get available generation modes for the current environment.
 */
export function getAvailableModes(): GenerationModeId[] {
  const settings = inferenceSettings as any;
  const config = detectEnvironment();
  return (settings.available_modes?.[config.environment] as GenerationModeId[]) ?? ["remote"];
}

/**
 * Get the default generation mode for the current environment.
 */
export function getDefaultMode(): GenerationModeId {
  const settings = inferenceSettings as any;
  const config = detectEnvironment();
  return (settings.default_mode?.[config.environment] as GenerationModeId) ?? "remote";
}

/**
 * Restore mode from sessionStorage, validating against available modes.
 * Falls back to default mode if stored value is invalid or sessionStorage unavailable.
 * (FR-017)
 */
export function restoreMode(
  availableModes: GenerationModeId[],
  defaultMode: GenerationModeId,
): GenerationModeId {
  try {
    const stored = sessionStorage.getItem("generation_mode");
    if (stored && availableModes.includes(stored as GenerationModeId)) {
      return stored as GenerationModeId;
    }
  } catch {
    // sessionStorage unavailable — fall back silently
  }
  return defaultMode;
}

/**
 * Check frontend-backend environment sync (FR-027).
 * Fetches GET /api/environment and logs a console warning if environments differ.
 */
export async function checkEnvironmentSync(): Promise<void> {
  const frontendConfig = detectEnvironment();
  try {
    const response = await sessionFetch("/environment", {}, { retryOn401: false });
    if (!response.ok) {
      console.warn("[Environment] Failed to fetch backend environment:", response.status);
      return;
    }
    const data = await response.json();
    const backendEnv = data?.environment;
    if (backendEnv && backendEnv !== frontendConfig.environment) {
      console.warn(
        `[Environment] Mismatch: frontend=${frontendConfig.environment}, backend=${backendEnv}. ` +
        `This may cause unexpected behavior. Check VITE_ENVIRONMENT and APP_ENV configuration.`
      );
    }
  } catch (error) {
    console.warn("[Environment] Could not verify backend environment:", error);
  }
}
