import ponyContract from "../../backend/pony_contract.json";

export const PONY_CONTRACT = ponyContract;

export type ImageMode = "txt2img" | "img2img";
export type OutputFormat = "png" | "jpeg";
export type Sampler =
  | "Euler a"
  | "DPM++ 2M Karras"
  | "DPM++ SDE Karras";

export interface ApiSettings {
  apiUrl: string;
  apiKey: string;
}

export interface GenerationPayload {
  model: "pony";
  type: "image";
  mode: ImageMode;
  prompt: string;
  negative_prompt: string;
  width: number;
  height: number;
  steps: number;
  cfg_scale: number;
  sampler: Sampler;
  clip_skip: number;
  denoising_strength: number;
  seed: number;
  output_format: OutputFormat;
  reference_image: string | null;
}

export interface ResultSummary {
  id: string;
  model: "pony";
  mode: ImageMode;
  prompt: string;
  negative_prompt: string;
  width: number;
  height: number;
  steps: number;
  cfg_scale: number;
  sampler: Sampler;
  clip_skip: number;
  denoising_strength: number;
  seed: number;
  output_format: OutputFormat;
  created_at: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: "pending" | "processing" | "done" | "failed" | "cancelled";
  message: string;
  result_url: string | null;
  preview_url: string | null;
  error: string | null;
  result: ResultSummary | null;
}

export interface GalleryItem extends ResultSummary {
  preview_url: string;
  result_url: string;
  thumbnailObjectUrl?: string;
}

export interface GalleryResponse {
  items: GalleryItem[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
}

const DEFAULT_API_URL = String(import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
const SETTINGS_KEY = "gooni_api_settings_v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function loadApiSettings(): ApiSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
    return {
      apiUrl: String(saved.apiUrl || DEFAULT_API_URL).replace(/\/+$/, ""),
      apiKey: String(saved.apiKey || ""),
    };
  } catch {
    return { apiUrl: DEFAULT_API_URL, apiKey: "" };
  }
}

export function saveApiSettings(settings: ApiSettings): ApiSettings {
  const normalized = {
    apiUrl: settings.apiUrl.trim().replace(/\/+$/, ""),
    apiKey: settings.apiKey.trim(),
  };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent("gooni-api-settings-changed"));
  return normalized;
}

function joinUrl(path: string): string {
  const { apiUrl } = loadApiSettings();
  if (!apiUrl) {
    throw new ApiError("Set the backend URL in Settings", 0);
  }
  return `${apiUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item: { loc?: string[]; msg?: string }) =>
          `${item.loc?.slice(1).join(".") || "request"}: ${item.msg || "invalid value"}`,
        )
        .join("; ");
    }
  } catch {
    // Fall back to the status line.
  }
  return `${response.status} ${response.statusText}`.trim();
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiKey } = loadApiSettings();
  const headers = new Headers(init.headers);
  if (apiKey) headers.set("X-API-Key", apiKey);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(joinUrl(path), { ...init, headers });
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  return response.json() as Promise<T>;
}

export async function testConnection(): Promise<void> {
  await apiRequest<{ models: unknown[] }>("/models");
}

export async function generateImage(
  payload: GenerationPayload,
): Promise<{ task_id: string; status: string; message: string }> {
  return apiRequest("/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return apiRequest(`/status/${encodeURIComponent(taskId)}`);
}

export async function cancelTask(taskId: string): Promise<TaskStatusResponse> {
  return apiRequest(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}

export async function getGallery(page = 1, perPage = 50): Promise<GalleryResponse> {
  return apiRequest(`/gallery?page=${page}&per_page=${perPage}`);
}

export async function deleteGalleryItem(id: string): Promise<void> {
  await apiRequest(`/gallery/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function fetchAsset(path: string): Promise<Blob> {
  const { apiKey } = loadApiSettings();
  const headers = new Headers();
  if (apiKey) headers.set("X-API-Key", apiKey);
  const response = await fetch(joinUrl(path), { headers });
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  return response.blob();
}
