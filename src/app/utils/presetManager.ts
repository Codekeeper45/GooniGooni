/**
 * Preset Manager — CRUD for user-created model parameter presets.
 * Presets persist in localStorage under key "gg_model_presets".
 */

const STORAGE_KEY = "gg_model_presets";

export interface ModelPreset {
  id: string;
  name: string;
  model_file: string;
  parameters: {
    steps: number;
    cfg_scale: number;
    sampler: string;
    scheduler: string;
    width: number;
    height: number;
    clip_skip: number;
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
}

function generateId(): string {
  return crypto.randomUUID();
}

function readPresets(): ModelPreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writePresets(presets: ModelPreset[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets));
}

export function getPresets(): ModelPreset[] {
  return readPresets();
}

export function getPresetById(id: string): ModelPreset | null {
  return readPresets().find((p) => p.id === id) ?? null;
}

export function getPresetsForModel(modelFile: string): ModelPreset[] {
  return readPresets().filter((p) => p.model_file === modelFile);
}

export function savePreset(
  preset: Omit<ModelPreset, "id" | "created_at" | "updated_at">
): ModelPreset {
  const now = new Date().toISOString();
  const newPreset: ModelPreset = {
    ...preset,
    id: generateId(),
    created_at: now,
    updated_at: now,
  };
  const all = readPresets();
  all.push(newPreset);
  writePresets(all);
  return newPreset;
}

export function updatePreset(
  id: string,
  updates: Partial<Omit<ModelPreset, "id" | "created_at">>
): ModelPreset {
  const all = readPresets();
  const idx = all.findIndex((p) => p.id === id);
  if (idx === -1) throw new Error(`Preset ${id} not found`);
  all[idx] = {
    ...all[idx],
    ...updates,
    updated_at: new Date().toISOString(),
  };
  writePresets(all);
  return all[idx];
}

export function deletePreset(id: string): void {
  const all = readPresets().filter((p) => p.id !== id);
  writePresets(all);
}

export function exportPresets(): string {
  return JSON.stringify(readPresets(), null, 2);
}

export function importPresets(json: string): number {
  const imported: ModelPreset[] = JSON.parse(json);
  if (!Array.isArray(imported)) throw new Error("Invalid preset format");

  const existing = readPresets();
  const existingIds = new Set(existing.map((p) => p.id));
  let count = 0;

  for (const preset of imported) {
    if (!preset.id || !preset.name || !preset.model_file || !preset.parameters) {
      continue;
    }
    if (existingIds.has(preset.id)) {
      // Update existing
      const idx = existing.findIndex((p) => p.id === preset.id);
      existing[idx] = { ...preset, updated_at: new Date().toISOString() };
    } else {
      existing.push(preset);
    }
    count++;
  }

  writePresets(existing);
  return count;
}
