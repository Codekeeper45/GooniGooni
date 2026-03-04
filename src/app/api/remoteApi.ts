/**
 * Remote Mode API client.
 * Implements GenerationClient for cloud-based generation via Modal backend.
 * Uses sessionFetch() for auth-aware requests.
 *
 * @module remoteApi
 */

import type { GenerationClient, GenerationParams, GenerationResult, ProgressUpdate } from "./apiFactory";
import { sessionFetch, ensureGenerationSession, readApiError } from "../utils/sessionClient";
import { configManager } from "../utils/configManager";

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

const POLL_INTERVAL_MS = 2000;

/** FR-021: retry up to 3 times with exponential backoff 1s → 2s → 4s */
const RETRY_ATTEMPTS = 3;
const RETRY_BASE_DELAY_MS = 1000;

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting for GPU worker...",
  pending: "Waiting for GPU worker...",
  dispatch: "Dispatching to worker...",
  model_resolve: "Resolving model...",
  pipeline_materialize: "Loading AI model...",
  loading_model: "Loading AI model...",
  preprocessing: "Preparing inputs...",
  generating_image: "Generating image...",
  generating: "Generating...",
  inference: "Generating...",
  artifact_write: "Saving result...",
  postprocessing: "Encoding result...",
  saving: "Saving to gallery...",
  done: "Complete!",
  failed: "Generation failed",
};

// ═══════════════════════════════════════════════════════════════════════════════
// RemoteGenerationClient
// ═══════════════════════════════════════════════════════════════════════════════

export class RemoteGenerationClient implements GenerationClient {
  private _progressCallback: ((progress: ProgressUpdate) => void) | null = null;
  private _aborted = false;
  private _currentTaskId: string | null = null;

  // ── GenerationClient interface ──────────────────────────────────────────────

  onProgress(callback: (progress: ProgressUpdate) => void): void {
    this._progressCallback = callback;
  }

  async checkAvailability(): Promise<boolean> {
    try {
      const resp = await sessionFetch("/health", {}, { retryOn401: false });
      return resp.ok;
    } catch {
      return false;
    }
  }

  async generate(params: GenerationParams): Promise<GenerationResult> {
    this._aborted = false;
    const startTime = Date.now();

    // FR-021: auto-retry with exponential backoff for transient errors
    let lastError: RemoteApiError | null = null;
    for (let attempt = 0; attempt <= RETRY_ATTEMPTS; attempt++) {
      if (this._aborted) {
        throw new RemoteApiError("Generation cancelled.", "cancelled", false);
      }

      if (attempt > 0) {
        // Exponential backoff: 1s, 2s, 4s
        const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
        const countdownSeconds = Math.ceil(delay / 1000);
        this._emitProgress(`Retrying in ${countdownSeconds}s... (attempt ${attempt}/${RETRY_ATTEMPTS})`, 0, 100);
        await this._sleep(delay);
      }

      try {
        return await this._executeGeneration(params, startTime);
      } catch (err: any) {
        if (err instanceof RemoteApiError) {
          // Don't retry 4xx errors (client errors)
          if (!err.isTransient) {
            throw err;
          }
          lastError = err;
        } else {
          lastError = new RemoteApiError(
            err?.message || "Unknown error during generation.",
            "unknown_error",
            true,
          );
        }
      }
    }

    // All retries exhausted — throw with isTransient: true for ErrorDisplay
    throw lastError ?? new RemoteApiError("Generation failed after retries.", "retries_exhausted", true);
  }

  private async _executeGeneration(params: GenerationParams, startTime: number): Promise<GenerationResult> {

    // Ensure session before generating
    await ensureGenerationSession();

    // Build payload using configManager
    const currentMode = "txt2img"; // Remote images are always txt2img for now
    const values: Record<string, any> = {
      prompt: params.prompt,
      negative_prompt: params.negative_prompt ?? "",
      width: params.width,
      height: params.height,
      seed: params.seed ?? -1,
      output_format: "png",
    };
    const payload = configManager.buildPayload(params.model, currentMode, values);

    this._emitProgress("queued", 0, 100);

    // Submit generation request
    const resp = await sessionFetch(
      "/generate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      { retryOn401: true },
    );

    if (!resp.ok) {
      const apiErr = await readApiError(resp, "Failed to start generation.");
      throw new RemoteApiError(
        `${apiErr.detail} ${apiErr.userAction}`.trim(),
        apiErr.code,
        resp.status >= 500,
      );
    }

    const data = await resp.json();
    const taskId = data.task_id;
    this._currentTaskId = taskId;

    // Poll for completion
    const result = await this._pollUntilComplete(taskId);

    return {
      imageData: result.url,
      generationId: taskId,
      model: params.model,
      mode: "remote",
      parameters: values,
      duration: Date.now() - startTime,
    };
  }

  async cancelGeneration(): Promise<void> {
    this._aborted = true;
    this._currentTaskId = null;
  }

  // ── Internals ───────────────────────────────────────────────────────────────

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private _emitProgress(stage: string, value: number, max: number): void {
    if (this._progressCallback) {
      this._progressCallback({
        stage: STAGE_LABELS[stage] ?? stage,
        value,
        max,
        percentage: max > 0 ? Math.round((value / max) * 100) : 0,
      });
    }
  }

  private async _pollUntilComplete(
    taskId: string,
  ): Promise<{ url: string; previewUrl?: string }> {
    return new Promise((resolve, reject) => {
      let consecutiveErrors = 0;
      const maxErrors = 5;

      const poll = async () => {
        if (this._aborted) {
          reject(new RemoteApiError("Generation cancelled.", "cancelled", false));
          return;
        }

        try {
          const resp = await sessionFetch(`/status/${taskId}`, {}, { retryOn401: true });

          if (!resp.ok) {
            const apiErr = await readApiError(resp, "Status check failed.");
            consecutiveErrors++;

            if (resp.status >= 400 && resp.status < 500) {
              reject(
                new RemoteApiError(
                  `${apiErr.detail} ${apiErr.userAction}`.trim(),
                  apiErr.code,
                  false,
                ),
              );
              return;
            }

            if (consecutiveErrors >= maxErrors) {
              reject(
                new RemoteApiError(
                  `${apiErr.detail} ${apiErr.userAction}`.trim(),
                  apiErr.code,
                  true,
                ),
              );
              return;
            }

            // Retry on next poll interval
            setTimeout(poll, POLL_INTERVAL_MS);
            return;
          }

          consecutiveErrors = 0;
          const data = await resp.json();
          const progress = Number(data.progress ?? 0);

          this._emitProgress(data.stage ?? "processing", progress, 100);

          if (data.status === "done") {
            resolve({
              url: data.result_url ?? `/api/results/${taskId}`,
              previewUrl: data.preview_url,
            });
            return;
          }

          if (data.status === "failed") {
            reject(
              new RemoteApiError(
                data.error_msg ?? "Generation failed.",
                "generation_failed",
                false,
              ),
            );
            return;
          }

          // Still processing — poll again
          setTimeout(poll, POLL_INTERVAL_MS);
        } catch (err: any) {
          consecutiveErrors++;
          if (consecutiveErrors >= maxErrors) {
            reject(
              new RemoteApiError(
                err?.message || "Connection lost during generation.",
                "network_error",
                true,
              ),
            );
            return;
          }
          setTimeout(poll, POLL_INTERVAL_MS);
        }
      };

      // Start first poll immediately
      poll();
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Error type
// ═══════════════════════════════════════════════════════════════════════════════

export class RemoteApiError extends Error {
  readonly code: string;
  readonly isTransient: boolean;

  constructor(message: string, code: string, isTransient: boolean) {
    super(message);
    this.name = "RemoteApiError";
    this.code = code;
    this.isTransient = isTransient;
  }
}
