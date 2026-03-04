import inferenceSettings from "../../inference_settings.json";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

export type ModelId = "pony" | "flux" | "anisora" | "phr00t";
export type GenerationType = "image" | "video";
export type GenerationModeId = "local" | "remote";

/** Per-environment list of available modes (from inference_settings.json). */
export interface AvailableModesMap {
  local: GenerationModeId[];
  production: GenerationModeId[];
}

/** Per-environment default mode (from inference_settings.json). */
export interface DefaultModeMap {
  local: GenerationModeId;
  production: GenerationModeId;
}

/** Local mode connection settings (from inference_settings.json). */
export interface LocalModeConfig {
  comfyui_url: string;
  websocket_url: string;
  health_check_interval_ms: number;
  connection_timeout_ms: number;
}

/** Remote mode connection settings (from inference_settings.json). */
export interface RemoteModeConfig {
  timeout_ms: number;
  retry_attempts: number;
  retry_base_delay_ms: number;
}

/** Workflow entry (from inference_settings.json). */
export interface WorkflowConfig {
  file: string;
  display_name: string;
  category: string;
}

export interface ModelMetadata {
  vram_min_gb: number;
  lora_base: 'sdxl' | 'flux' | null;
  quality_tags: string | null;
}

interface ModelConfig {
  id: string;
  name: string;
  type: GenerationType;
  category: string;
  description: string;
  modes: Record<string, ModeConfig>;
  default_mode: string;
  parameters: Record<string, ParameterConfig>;
  fixed_parameters?: Record<string, FixedParameterConfig>;
  recommended_resolutions: ResolutionConfig[];
  metadata?: ModelMetadata;
}

interface ModeConfig {
  label: string;
  description: string;
  requires_reference: boolean;
  requires_multiple?: boolean;
}

interface ParameterConfig {
  type: "int" | "float" | "string" | "enum" | "image_upload";
  default?: any;
  min?: number;
  max?: number;
  step?: number;
  options?: any[];
  label: string;
  advanced: boolean;
  required_if?: string;
  visible_if?: string;
  help?: string;
  placeholder?: string;
  maxLength?: number;
  accepts?: string[];
}

interface FixedParameterConfig {
  value: any;
  locked: boolean;
  recommended?: boolean;
  warning: string;
}

interface ResolutionConfig {
  width: number;
  height: number;
  label: string;
}

export interface NormalizedResolution {
  width: number;
  height: number;
  changed: boolean;
  reason?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Config Manager
// ═══════════════════════════════════════════════════════════════════════════════

export class InferenceConfigManager {
  private config: typeof inferenceSettings;

  constructor() {
    this.config = inferenceSettings;
  }

  private evaluateModeCondition(condition: string, mode: string): boolean {
    const orParts = condition.split("||").map((p) => p.trim()).filter(Boolean);
    if (orParts.length === 0) return true;

    return orParts.some((orPart) => {
      const andParts = orPart.split("&&").map((p) => p.trim()).filter(Boolean);
      return andParts.every((part) => this.evaluateAtomicCondition(part, mode));
    });
  }

  private evaluateAtomicCondition(part: string, mode: string): boolean {
    const match = part.match(/^mode\s*(==|!=)\s*['"]?([a-zA-Z0-9_]+)['"]?$/);
    if (!match) return false;
    const [, op, value] = match;
    return op === "==" ? mode === value : mode !== value;
  }

  // ─── Get all models ─────────────────────────────────────────────────────────
  getAllModels(): ModelConfig[] {
    const imageModels = Object.values(this.config.image_models);
    const videoModels = Object.values(this.config.video_models);
    return [...imageModels, ...videoModels] as ModelConfig[];
  }

  // ─── Get model by ID ────────────────────────────────────────────────────────
  getModel(modelId: ModelId): ModelConfig | null {
    const allModels = this.getAllModels();
    return allModels.find((m) => m.id === modelId) || null;
  }

  // ─── Get models by type ─────────────────────────────────────────────────────
  getModelsByType(type: GenerationType): ModelConfig[] {
    return this.getAllModels().filter((m) => m.type === type);
  }

  // Backward-compat helper used by ControlPanel summary UI.
  getModelLabel(type: GenerationType, modelId: string): string {
    const model = this.getModel(modelId as ModelId);
    if (model?.name) return model.name;

    const fallback = String(modelId || "").trim();
    if (fallback) return fallback;

    return type === "video" ? "Video model" : "Image model";
  }

  // ─── Get modes for model ────────────────────────────────────────────────────
  getModesForModel(modelId: ModelId): Record<string, ModeConfig> {
    const model = this.getModel(modelId);
    return model?.modes || {};
  }

  // ─── Get default mode for model ─────────────────────────────────────────────
  getDefaultMode(modelId: ModelId): string {
    const model = this.getModel(modelId);
    return model?.default_mode || "t2v";
  }

  // ─── Get parameters for model ───────────────────────────────────────────────
  getParameters(modelId: ModelId): Record<string, ParameterConfig> {
    const model = this.getModel(modelId);
    return model?.parameters || {};
  }

  // ─── Get fixed parameters ───────────────────────────────────────────────────
  getFixedParameters(modelId: ModelId): Record<string, FixedParameterConfig> {
    const model = this.getModel(modelId);
    return model?.fixed_parameters || {};
  }

  // ─── Get visible parameters for mode ────────────────────────────────────────
  getVisibleParameters(
    modelId: ModelId,
    mode: string,
    advanced: boolean
  ): Record<string, ParameterConfig> {
    const allParams = this.getParameters(modelId);
    const visible: Record<string, ParameterConfig> = {};

    Object.entries(allParams).forEach(([key, param]) => {
      // Check advanced filter
      if (!advanced && param.advanced) return;

      // Check visibility condition
      if (param.visible_if) {
        if (!this.evaluateModeCondition(param.visible_if, mode)) return;
      }

      visible[key] = param;
    });

    return visible;
  }

  // ─── Check if parameter is required ─────────────────────────────────────────
  isParameterRequired(
    modelId: ModelId,
    paramKey: string,
    mode: string
  ): boolean {
    const params = this.getParameters(modelId);
    const param = params[paramKey];

    if (!param) return false;

    if (param.required_if) {
      return this.evaluateModeCondition(param.required_if, mode);
    }

    return false;
  }

  // ─── Get default value for parameter ────────────────────────────────────────
  getDefaultValue(modelId: ModelId, paramKey: string): any {
    const params = this.getParameters(modelId);
    return params[paramKey]?.default;
  }

  // ─── Get common parameters ──────────────────────────────────────────────────
  getCommonParameters(): Record<string, ParameterConfig> {
    return this.config.common as any;
  }

  // ─── Get recommended resolutions ────────────────────────────────────────────
  getRecommendedResolutions(modelId: ModelId): ResolutionConfig[] {
    const model = this.getModel(modelId);
    return model?.recommended_resolutions || [];
  }

  getPreferredInitialResolution(modelId: ModelId): ResolutionConfig {
    const recommended = this.getRecommendedResolutions(modelId);
    if (recommended.length === 0) {
      return modelId === "pony"
        ? { width: 1024, height: 1024, label: "1024x1024" }
        : { width: 768, height: 768, label: "768x768" };
    }

    if (modelId === "pony") {
      const ponyPreferred = recommended.find(
        (item) => item.width === 1024 && item.height === 1024,
      );
      if (ponyPreferred) return ponyPreferred;
    }

    return recommended[0];
  }

  isSafeImageResolution(modelId: ModelId, width: number, height: number): boolean {
    const model = this.getModel(modelId);
    if (!model || model.type !== "image") return true;

    const recommended = this.getRecommendedResolutions(modelId);
    const exactRecommended = recommended.some(
      (item) => item.width === width && item.height === height,
    );
    if (exactRecommended) return true;

    if (modelId === "pony") {
      return width === height && width >= 512 && width <= 1024;
    }

    return width === height && width >= 512 && width <= 1024;
  }

  normalizeImageResolution(
    modelId: ModelId,
    width: number,
    height: number,
  ): NormalizedResolution {
    const model = this.getModel(modelId);
    if (!model || model.type !== "image") {
      return { width, height, changed: false };
    }

    const preferred = this.getPreferredInitialResolution(modelId);
    const isKnownVideoPreset = [
      [720, 1280],
      [1280, 720],
      [896, 1120],
      [1152, 720],
    ].some(([w, h]) => width === w && height === h);

    const exactRecommended = this.getRecommendedResolutions(modelId).some(
      (item) => item.width === width && item.height === height,
    );
    const isSquare = width === height;

    if (exactRecommended && !isKnownVideoPreset) {
      return { width, height, changed: false };
    }

    if (modelId === "pony") {
      if (this.isSafeImageResolution(modelId, width, height) && !isKnownVideoPreset) {
        return { width, height, changed: false };
      }

      const maxSide = Math.max(width, height);
      const side = maxSide > 896 ? 1024 : maxSide > 640 ? 768 : 512;
      return {
        width: side,
        height: side,
        changed: width !== side || height !== side,
        reason: "Pony uses square-safe SDXL resolutions for stability.",
      };
    }

    if (this.isSafeImageResolution(modelId, width, height) && !isKnownVideoPreset && isSquare) {
      return { width, height, changed: false };
    }

    return {
      width: preferred.width,
      height: preferred.height,
      changed: width !== preferred.width || height !== preferred.height,
      reason: `${model.name} uses recommended image-safe resolutions.`,
    };
  }

  // ─── Build payload for API ──────────────────────────────────────────────────

  // ─── Mode-aware config (hybrid mode) ────────────────────────────────────────

  /** Returns the available_modes map from inference_settings.json. */
  getAvailableModesMap(): AvailableModesMap {
    const cfg = this.config as any;
    return (cfg.available_modes ?? { local: ["local", "remote"], production: ["remote"] }) as AvailableModesMap;
  }

  /** Returns the default_mode map from inference_settings.json. */
  getDefaultModeMap(): DefaultModeMap {
    const cfg = this.config as any;
    return (cfg.default_mode ?? { local: "local", production: "remote" }) as DefaultModeMap;
  }

  /** Returns local_mode settings from inference_settings.json. */
  getLocalModeConfig(): LocalModeConfig {
    const cfg = this.config as any;
    return (cfg.local_mode ?? {
      comfyui_url: "http://127.0.0.1:8188",
      websocket_url: "ws://127.0.0.1:8188/ws",
      health_check_interval_ms: 10000,
      connection_timeout_ms: 5000,
    }) as LocalModeConfig;
  }

  /** Returns remote_mode settings from inference_settings.json. */
  getRemoteModeConfig(): RemoteModeConfig {
    const cfg = this.config as any;
    return (cfg.remote_mode ?? {
      timeout_ms: 60000,
      retry_attempts: 3,
      retry_base_delay_ms: 1000,
    }) as RemoteModeConfig;
  }

  /** Returns workflow definitions from inference_settings.json, keyed by model. */
  getWorkflows(): Record<string, WorkflowConfig> {
    const cfg = this.config as any;
    return (cfg.workflows ?? {}) as Record<string, WorkflowConfig>;
  }

  /** Returns workflow config for a specific model, or null if not found. */
  getWorkflowForModel(modelId: string): WorkflowConfig | null {
    const workflows = this.getWorkflows();
    return workflows[modelId] ?? null;
  }

  // ──────────────────────────────────────────────────────────────────────────────

  buildPayload(
    modelId: ModelId,
    mode: string,
    values: Record<string, any>
  ): Record<string, any> {
    const model = this.getModel(modelId);
    if (!model) return {};

    const payload: Record<string, any> = {
      model: modelId,
      type: model.type,
      mode,
    };

    // Add common parameters
    const commonParams = this.getCommonParameters();
    Object.keys(commonParams).forEach((key) => {
      if (values[key] !== undefined) {
        payload[key] = values[key];
      }
    });

    // Add model-specific parameters
    const modelParams = this.getParameters(modelId);
    Object.keys(modelParams).forEach((key) => {
      if (values[key] !== undefined) {
        // Check visibility
        const param = modelParams[key];
        if (param.visible_if) {
          if (!this.evaluateModeCondition(param.visible_if, mode)) return;
        }
        payload[key] = values[key];
      }
    });

    // Add fixed parameters
    const fixedParams = this.getFixedParameters(modelId);
    Object.entries(fixedParams).forEach(([key, config]) => {
      payload[key] = config.value;
    });

    return payload;
  }

  // ─── Validate values ────────────────────────────────────────────────────────
  validateValues(
    modelId: ModelId,
    mode: string,
    values: Record<string, any>
  ): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    const params = this.getParameters(modelId);
    const fixedParams = this.getFixedParameters(modelId);

    Object.entries(fixedParams).forEach(([key, fixed]) => {
      const value = values[key];
      if (!fixed.locked || value === undefined || value === null || value === "") return;
      if (value !== fixed.value) {
        errors.push(`${key} must be ${fixed.value}`);
      }
    });

    Object.entries(params).forEach(([key, param]) => {
      const value = values[key];

      // Check required
      if (this.isParameterRequired(modelId, key, mode) && (value === undefined || value === null || value === "")) {
        errors.push(`${param.label} is required`);
      }

      // Check range
      if (value !== undefined && (param.type === "int" || param.type === "float")) {
        if (param.min !== undefined && value < param.min) {
          errors.push(`${param.label} must be at least ${param.min}`);
        }
        if (param.max !== undefined && value > param.max) {
          errors.push(`${param.label} must be at most ${param.max}`);
        }
      }

      // Check enum
      if (param.type === "enum" && value !== undefined) {
        if (!param.options?.includes(value)) {
          errors.push(`${param.label} must be one of: ${param.options?.join(", ")}`);
        }
      }
    });

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  // ─── Calculate estimate ─────────────────────────────────────────────────────
  calculateEstimate(
    modelId: ModelId,
    values: Record<string, any>
  ): number {
    const model = this.getModel(modelId);
    if (!model) return 0;

    if (model.type === "video") {
      const numFrames = values.num_frames || 81;
      const fps = values.fps || 16;
      return Math.round((numFrames / fps) * 3.5);
    } else {
      const steps = values.steps || 30;
      return Math.round(steps * 0.4);
    }
  }

  // ─── Get model defaults (flat key→value map) ───────────────────────────────
  getModelDefaults(modelId: ModelId): Record<string, any> {
    const model = this.getModel(modelId);
    if (!model) return {};

    const defaults: Record<string, any> = {};

    // Extract defaults from parameters
    Object.entries(model.parameters).forEach(([key, param]) => {
      if (param.default !== undefined) {
        defaults[key] = param.default;
      }
    });

    // Apply fixed parameter values (override tunables)
    if (model.fixed_parameters) {
      Object.entries(model.fixed_parameters).forEach(([key, fixed]) => {
        defaults[key] = fixed.value;
      });
    }

    // Add resolution defaults from recommended resolutions
    const resolution = this.getPreferredInitialResolution(modelId);
    defaults.width = resolution.width;
    defaults.height = resolution.height;

    return defaults;
  }

  // ─── Get model metadata (VRAM, LoRA base, quality tags) ────────────────────
  getModelMetadata(modelId: ModelId): ModelMetadata | null {
    const model = this.getModel(modelId);
    return model?.metadata ?? null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Singleton instance
// ═══════════════════════════════════════════════════════════════════════════════

export const configManager = new InferenceConfigManager();

// ═══════════════════════════════════════════════════════════════════════════════
// Helper hooks
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Hook to get model config
 */
export function useModelConfig(modelId: ModelId | null) {
  if (!modelId) return null;
  return configManager.getModel(modelId);
}

/**
 * Hook to get parameter config
 */
export function useParameterConfig(
  modelId: ModelId | null,
  paramKey: string
) {
  if (!modelId) return null;
  const params = configManager.getParameters(modelId);
  return params[paramKey] || null;
}

/**
 * Hook to get visible parameters
 */
export function useVisibleParameters(
  modelId: ModelId | null,
  mode: string,
  advanced: boolean
) {
  if (!modelId) return {};
  return configManager.getVisibleParameters(modelId, mode, advanced);
}
