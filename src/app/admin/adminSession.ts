const ADMIN_SESSION_KEY = "gg_admin_session";
const REQUEST_TIMEOUT_MS = 30000;
const ADMIN_API_BASE = "/api";

export interface AdminSession {
  authenticated: true;
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
  try {
    return localStorage.getItem(ADMIN_SESSION_KEY) === "1" ? { authenticated: true } : null;
  } catch {
    return null;
  }
}

export function saveSession(): void {
  localStorage.setItem(ADMIN_SESSION_KEY, "1");
}

export function clearSession(): void {
  localStorage.removeItem(ADMIN_SESSION_KEY);
}

export function isLoggedIn(): boolean {
  return !!getSession();
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (payload?.detail?.detail) return payload.detail.detail as string;
    if (typeof payload?.detail === "string") return payload.detail;
  } catch {
    // ignore parse errors
  }
  return `HTTP ${response.status}`;
}

export async function createAdminSession(login: string, password: string): Promise<void> {
  const response = await fetchAdmin("/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login, password }),
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  saveSession();
}

export async function ensureAdminSession(): Promise<void> {
  const response = await fetchAdmin("/admin/session", {
    method: "GET",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
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
  const session = getSession();
  if (!session) throw new Error("Not authenticated");

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
