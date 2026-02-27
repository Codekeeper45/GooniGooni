const REQUEST_TIMEOUT_MS = 30000;
const ADMIN_API_BASE = "/api";

export interface AdminSession {
  authenticated: true;
}

export interface AdminErrorPayload {
  status: number;
  code?: string;
  detail: string;
}

const ADMIN_SESSION_ERROR_CODES = new Set([
  "admin_session_missing",
  "admin_session_expired",
  "admin_session_invalid",
]);

export class AdminHttpError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(payload: AdminErrorPayload) {
    super(payload.detail);
    this.name = "AdminHttpError";
    this.status = payload.status;
    this.code = payload.code;
  }
}

function getAdminApiUrl(path: string, base: string = ADMIN_API_BASE): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${normalized}` : normalized;
}

function getAdminApiBases(): string[] {
  if (typeof window !== "undefined" && window.location.hostname.endsWith("modal.run")) {
    // On direct Modal URL there is no nginx /api proxy, so allow a direct-path fallback.
    return ["/api", ""];
  }
  return ["/api"];
}

async function fetchAdmin(path: string, init: RequestInit): Promise<Response> {
  const bases = getAdminApiBases();
  let lastError: unknown = null;

  for (const base of bases) {
    const url = getAdminApiUrl(path, base);
    try {
      const response = await fetch(url, init);
      if (base === "/api" && response.status === 404 && bases.length > 1) {
        continue;
      }
      return response;
    } catch (error) {
      lastError = error;
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }
  throw new Error("Failed to reach admin API");
}

export function getSession(): AdminSession | null {
  return { authenticated: true };
}

export function saveSession(): void {
  // server-side cookie is the source of truth
}

export function clearSession(): void {
  // server-side cookie is the source of truth
}

export function isLoggedIn(): boolean {
  return true;
}

export function isAdminSessionErrorCode(code?: string): boolean {
  return !!code && ADMIN_SESSION_ERROR_CODES.has(code);
}

async function parseErrorPayload(response: Response): Promise<AdminErrorPayload> {
  try {
    const payload = await response.json();
    if (payload?.detail && typeof payload.detail === "object") {
      return {
        status: response.status,
        code: typeof payload.detail.code === "string" ? payload.detail.code : undefined,
        detail:
          typeof payload.detail.detail === "string"
            ? payload.detail.detail
            : `HTTP ${response.status}`,
      };
    }
    if (typeof payload?.detail === "string") {
      return { status: response.status, detail: payload.detail };
    }
  } catch {
    // ignore parse errors
  }
  return { status: response.status, detail: `HTTP ${response.status}` };
}

export async function readAdminErrorPayload(response: Response): Promise<AdminErrorPayload> {
  return parseErrorPayload(response);
}

export async function createAdminSession(login: string, password: string): Promise<void> {
  const response = await fetchAdmin("/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login, password }),
    credentials: "include",
  });
  if (!response.ok) {
    throw new AdminHttpError(await parseErrorPayload(response));
  }
}

export async function ensureAdminSession(): Promise<void> {
  const response = await fetchAdmin("/admin/session", {
    method: "GET",
    credentials: "include",
  });
  if (!response.ok) {
    throw new AdminHttpError(await parseErrorPayload(response));
  }
}

export async function revokeAdminSession(): Promise<void> {
  await fetchAdmin("/admin/session", {
    method: "DELETE",
    credentials: "include",
  });
}

export async function adminFetch(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string> | undefined) ?? {}),
    };

    return await fetchAdmin(path, {
      ...options,
      credentials: "include",
      signal: options.signal ?? controller.signal,
      headers,
    });
  } finally {
    clearTimeout(timeout);
  }
}
