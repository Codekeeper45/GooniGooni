/**
 * API Client Factory — mode-based client dispatch.
 * Returns the appropriate GenerationClient based on the selected generation mode.
 * @module apiFactory
 */

// ═══════════════════════════════════════════════════════════════════════════════
// Interfaces
// ═══════════════════════════════════════════════════════════════════════════════

export interface GenerationParams {
  model: "pony" | "flux";
  prompt: string;
  negative_prompt?: string;
  width: number;
  height: number;
  seed?: number;
  /** Local Mode only; defaults per workflow (Pony: 25, Flux: 20) */
  steps?: number;
  /** Local Mode only; defaults per workflow (Pony: 7.0, Flux: forced 1.0) */
  cfg_scale?: number;
  /** LoRA configurations to inject into the workflow */
  loras?: Array<{
    path: string;
    filename: string;
    strength_model: number;
    strength_clip: number;
  }>;
}

export interface GenerationResult {
  imageData: string;
  generationId: string;
  model: string;
  mode: "local" | "remote";
  parameters: Record<string, any>;
  duration: number;
}

export interface ProgressUpdate {
  stage: string;
  value: number;
  max: number;
  percentage: number;
}

export interface GenerationClient {
  generate(params: GenerationParams): Promise<GenerationResult>;
  cancelGeneration(): Promise<void>;
  onProgress(callback: (progress: ProgressUpdate) => void): void;
  checkAvailability(): Promise<boolean>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Client registry
// ═══════════════════════════════════════════════════════════════════════════════

let _remoteClient: GenerationClient | null = null;
let _localClient: GenerationClient | null = null;

/**
 * Set the Remote Mode client implementation.
 * Called during app initialization.
 */
export function registerRemoteClient(client: GenerationClient): void {
  _remoteClient = client;
}

/**
 * Set the Local Mode client implementation.
 * Called during app initialization (dev only).
 */
export function registerLocalClient(client: GenerationClient): void {
  _localClient = client;
}

/**
 * Get the appropriate API client for the given mode.
 *
 * In production builds, requesting "local" mode will throw an error
 * because the ComfyUI client is tree-shaken out of the bundle.
 */
export async function getAPIClient(mode: "local" | "remote"): Promise<GenerationClient> {
  if (mode === "remote") {
    if (!_remoteClient) {
      // Lazy-load remote client
      const { RemoteGenerationClient } = await import("./remoteApi");
      _remoteClient = new RemoteGenerationClient();
    }
    return _remoteClient!;
  }

  if (mode === "local") {
    // In production, ComfyUI code is excluded via import.meta.env.DEV guard
    if (import.meta.env.DEV) {
      if (!_localClient) {
        const { ComfyUIClient } = await import(/* @vite-ignore */ "./comfyApi");
        _localClient = new ComfyUIClient();
      }
      return _localClient!;
    }
    throw new Error("Local Mode is not available in production environment.");
  }

  throw new Error(`Unknown generation mode: ${mode}`);
}
