/**
 * ComfyUI API client — Local Mode generation via ComfyUI on localhost:8188.
 * Implements GenerationClient interface.
 * Uses Vite dev proxy /comfy-api for REST and direct WebSocket for progress.
 *
 * @module comfyApi
 */

import type { GenerationClient, GenerationParams, GenerationResult, ProgressUpdate } from "./apiFactory";
import { configManager } from "../utils/configManager";

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

const COMFY_REST_BASE = "/comfy-api";

// ═══════════════════════════════════════════════════════════════════════════════
// ComfyUIClient
// ═══════════════════════════════════════════════════════════════════════════════

export class ComfyUIClient implements GenerationClient {
  private _progressCallback: ((progress: ProgressUpdate) => void) | null = null;
  private _ws: WebSocket | null = null;
  private _clientId: string;
  private _aborted = false;
  private _currentPromptId: string | null = null;

  constructor() {
    this._clientId = crypto.randomUUID();
  }

  // ── GenerationClient interface ──────────────────────────────────────────────

  onProgress(callback: (progress: ProgressUpdate) => void): void {
    this._progressCallback = callback;
  }

  async checkAvailability(): Promise<boolean> {
    try {
      const resp = await fetch(`${COMFY_REST_BASE}/system_stats`);
      return resp.ok;
    } catch {
      return false;
    }
  }

  async generate(params: GenerationParams): Promise<GenerationResult> {
    this._aborted = false;
    const startTime = Date.now();

    // Load and prepare workflow
    const workflow = await this._loadWorkflow(params.model);
    const injected = this._injectParameters(workflow, params);
    const validated = this._validateWorkflow(injected);
    if (validated.length > 0) {
      throw new ComfyUIError(
        `Invalid workflow configuration for ${params.model}: ${validated.join(", ")}`,
        "workflow_validation_failed",
      );
    }

    this._emitProgress("Submitting to ComfyUI...", 0, 100);

    // Submit workflow prompt
    const promptResp = await fetch(`${COMFY_REST_BASE}/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: injected,
        client_id: this._clientId,
      }),
    });

    if (!promptResp.ok) {
      const text = await promptResp.text().catch(() => "Unknown error");
      throw new ComfyUIError(
        `ComfyUI rejected the workflow: ${text}`,
        "prompt_rejected",
      );
    }

    const promptData = await promptResp.json();
    this._currentPromptId = promptData.prompt_id;

    // Listen for completion via WebSocket
    const result = await this._waitForCompletion(promptData.prompt_id, params);

    return {
      imageData: result.imageUrl,
      generationId: promptData.prompt_id,
      model: params.model,
      mode: "local",
      parameters: { ...params },
      duration: Date.now() - startTime,
    };
  }

  async cancelGeneration(): Promise<void> {
    this._aborted = true;

    // Interrupt currently executing generation
    try {
      await fetch(`${COMFY_REST_BASE}/interrupt`, { method: "POST" });
    } catch {
      // Best effort
    }

    // Clear ComfyUI queue
    try {
      await fetch(`${COMFY_REST_BASE}/queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clear: true }),
      });
    } catch {
      // Best effort
    }

    this._closeWebSocket();
    this._currentPromptId = null;
  }

  // ── Workflow Management ─────────────────────────────────────────────────────

  private async _loadWorkflow(modelKey: string): Promise<Record<string, any>> {
    const workflowConfig = configManager.getWorkflowForModel(modelKey);
    if (!workflowConfig) {
      throw new ComfyUIError(
        `Invalid workflow configuration for ${modelKey}`,
        "workflow_not_found",
      );
    }

    try {
      // Fetch workflow JSON from the workflows directory
      const resp = await fetch(`/${workflowConfig.file}`);
      if (!resp.ok) {
        throw new ComfyUIError(
          `Invalid workflow configuration for ${modelKey}`,
          "workflow_fetch_failed",
        );
      }
      return await resp.json();
    } catch (err) {
      if (err instanceof ComfyUIError) throw err;
      throw new ComfyUIError(
        `Failed to load workflow for ${modelKey}: ${(err as Error).message}`,
        "workflow_load_error",
      );
    }
  }

  private _injectParameters(
    workflow: Record<string, any>,
    params: GenerationParams,
  ): Record<string, any> {
    const injected = JSON.parse(JSON.stringify(workflow));

    // Node mapping per data-model.md:
    // 6 → CLIPTextEncode (positive prompt)
    // 7 → CLIPTextEncode (negative prompt)
    // 3 → KSampler (seed, steps, cfg)
    // 5 → EmptyLatentImage / EmptySD3LatentImage (width, height)

    if (injected["6"]?.inputs) {
      injected["6"].inputs.text = params.prompt;
    }

    if (injected["7"]?.inputs) {
      // Flux uses empty negative prompt
      injected["7"].inputs.text =
        params.model === "flux" ? "" : (params.negative_prompt ?? "");
    }

    if (injected["3"]?.inputs) {
      if (params.seed !== undefined && params.seed >= 0) {
        injected["3"].inputs.seed = params.seed;
      } else {
        injected["3"].inputs.seed = Math.floor(Math.random() * 2147483647);
      }

      if (params.steps !== undefined) {
        injected["3"].inputs.steps = params.steps;
      }

      if (params.cfg_scale !== undefined) {
        // Flux: force cfg to 1.0
        injected["3"].inputs.cfg =
          params.model === "flux" ? 1.0 : params.cfg_scale;
      }
    }

    if (injected["5"]?.inputs) {
      injected["5"].inputs.width = params.width;
      injected["5"].inputs.height = params.height;
    }

    return injected;
  }

  private _validateWorkflow(workflow: Record<string, any>): string[] {
    const errors: string[] = [];

    // Check required nodes exist
    const requiredNodes = ["3", "5", "6"];
    for (const nodeId of requiredNodes) {
      if (!workflow[nodeId]) {
        errors.push(`Missing required node ${nodeId}`);
        continue;
      }
      if (typeof workflow[nodeId].class_type !== "string") {
        errors.push(`Node ${nodeId} missing class_type`);
      }
      if (!workflow[nodeId].inputs) {
        errors.push(`Node ${nodeId} missing inputs`);
      }
    }

    return errors;
  }

  // ── WebSocket Progress ──────────────────────────────────────────────────────

  private _waitForCompletion(
    promptId: string,
    params: GenerationParams,
  ): Promise<{ imageUrl: string }> {
    const MAX_WS_RECONNECTS = 3;
    const WS_RECONNECT_DELAY_MS = 2000;

    return new Promise((resolve, reject) => {
      const localConfig = configManager.getLocalModeConfig();
      const wsUrl = `${localConfig.websocket_url}?clientId=${this._clientId}`;
      let reconnectAttempts = 0;
      let settled = false;

      const overallTimeout = setTimeout(() => {
        if (settled) return;
        settled = true;
        this._closeWebSocket();
        reject(
          new ComfyUIError(
            "Generation timed out waiting for ComfyUI",
            "generation_timeout",
          ),
        );
      }, localConfig.connection_timeout_ms + 300_000); // 5min + connection timeout

      const connectWs = () => {
        if (settled) return;

        try {
          this._ws = new WebSocket(wsUrl);
        } catch (err) {
          if (settled) return;
          settled = true;
          clearTimeout(overallTimeout);
          reject(
            new ComfyUIError(
              "Failed to connect to ComfyUI WebSocket",
              "websocket_connect_failed",
            ),
          );
          return;
        }

        this._ws.onmessage = (event) => {
          if (settled) return;
          try {
            const data = JSON.parse(event.data);

            if (data.type === "progress" && data.data?.prompt_id === promptId) {
              const value = data.data.value ?? 0;
              const max = data.data.max ?? 100;
              this._emitProgress("Generating...", value, max);
            }

            if (data.type === "executing" && data.data?.prompt_id === promptId) {
              if (data.data.node === null) {
                // Execution complete — fetch the output image
                settled = true;
                clearTimeout(overallTimeout);
                this._closeWebSocket();
                this._fetchOutputImage(promptId)
                  .then((imageUrl) => resolve({ imageUrl }))
                  .catch(reject);
              }
            }

            if (data.type === "execution_error" && data.data?.prompt_id === promptId) {
              settled = true;
              clearTimeout(overallTimeout);
              this._closeWebSocket();
              reject(
                new ComfyUIError(
                  `ComfyUI execution error: ${data.data.exception_message ?? "Unknown"}`,
                  "execution_error",
                ),
              );
            }
          } catch {
            // Ignore non-JSON messages
          }
        };

        this._ws.onerror = () => {
          if (settled) return;
          this._closeWebSocket();
          attemptReconnect();
        };

        this._ws.onclose = () => {
          if (settled) return;
          if (this._aborted) {
            settled = true;
            clearTimeout(overallTimeout);
            reject(new ComfyUIError("Generation cancelled.", "cancelled"));
            return;
          }
          // Unexpected close — try to reconnect
          attemptReconnect();
        };
      };

      const attemptReconnect = () => {
        if (settled || this._aborted) return;
        reconnectAttempts++;
        if (reconnectAttempts > MAX_WS_RECONNECTS) {
          settled = true;
          clearTimeout(overallTimeout);
          reject(
            new ComfyUIError(
              "ComfyUI WebSocket connection lost after multiple retries",
              "websocket_error",
            ),
          );
          return;
        }
        this._emitProgress(`Reconnecting (${reconnectAttempts}/${MAX_WS_RECONNECTS})...`, 0, 100);
        setTimeout(connectWs, WS_RECONNECT_DELAY_MS);
      };

      connectWs();
    });
  }

  private async _fetchOutputImage(promptId: string): Promise<string> {
    // Get history to find the output filename
    const histResp = await fetch(`${COMFY_REST_BASE}/history/${promptId}`);
    if (!histResp.ok) {
      throw new ComfyUIError(
        "Failed to retrieve generation result from ComfyUI",
        "history_fetch_failed",
      );
    }

    const history = await histResp.json();
    const outputs = history[promptId]?.outputs;
    if (!outputs) {
      throw new ComfyUIError(
        "No output found in ComfyUI history",
        "no_output",
      );
    }

    // Find the first images output
    for (const nodeId of Object.keys(outputs)) {
      const images = outputs[nodeId]?.images;
      if (images && images.length > 0) {
        const img = images[0];
        // Return blob URL via /comfy-api/view
        const viewUrl = `${COMFY_REST_BASE}/view?filename=${encodeURIComponent(img.filename)}&subfolder=${encodeURIComponent(img.subfolder ?? "")}&type=${encodeURIComponent(img.type ?? "output")}`;
        
        // Fetch and create blob URL for display
        const imgResp = await fetch(viewUrl);
        if (!imgResp.ok) {
          throw new ComfyUIError(
            "Failed to fetch generated image from ComfyUI",
            "image_fetch_failed",
          );
        }
        const blob = await imgResp.blob();
        return URL.createObjectURL(blob);
      }
    }

    throw new ComfyUIError(
      "No images found in ComfyUI output",
      "no_images",
    );
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  private _emitProgress(stage: string, value: number, max: number): void {
    if (this._progressCallback) {
      this._progressCallback({
        stage,
        value,
        max,
        percentage: max > 0 ? Math.round((value / max) * 100) : 0,
      });
    }
  }

  private _closeWebSocket(): void {
    if (this._ws) {
      try {
        this._ws.close();
      } catch {
        // Ignore
      }
      this._ws = null;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Error type
// ═══════════════════════════════════════════════════════════════════════════════

export class ComfyUIError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "ComfyUIError";
    this.code = code;
  }
}
