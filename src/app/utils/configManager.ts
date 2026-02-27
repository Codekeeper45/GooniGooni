import inferenceSettings from "../../inference_settings.json";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

export type ModelId = "pony" | "flux" | "anisora" | "phr00t";
export type GenerationType = "image" | "video";

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

  // ─── Build payload for API ──────────────────────────────────────────────────
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
