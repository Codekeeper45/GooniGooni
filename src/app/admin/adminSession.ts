const ADMIN_API_URL_KEY = "gg_admin_api_url";
const ADMIN_AUTH_MODE_KEY = "gg_admin_auth_mode";
const ADMIN_FALLBACK_KEY = "gg_admin_fallback_key";
const REQUEST_TIMEOUT_MS = 30000;

export type AdminAuthMode = "cookie" | "header";

export interface AdminSession {
  apiUrl: string;
  authMode: AdminAuthMode;
  adminKey?: string;
}

function normalizeApiUrl(apiUrl: string): string {
  return apiUrl.trim().replace(/\/$/, "");
}

export function getSession(): AdminSession | null {
  try {
    const apiUrl = localStorage.getItem(ADMIN_API_URL_KEY) ?? "";
    if (!apiUrl) return null;
    const authMode = (localStorage.getItem(ADMIN_AUTH_MODE_KEY) as AdminAuthMode | null) ?? "cookie";
    const adminKey = localStorage.getItem(ADMIN_FALLBACK_KEY) ?? "";
    return {
      apiUrl,
      authMode,
      adminKey: authMode === "header" ? adminKey : undefined,
    };
  } catch {
    return null;
  }
}

export function saveSession(session: AdminSession): void {
  localStorage.setItem(ADMIN_API_URL_KEY, normalizeApiUrl(session.apiUrl));
  localStorage.setItem(ADMIN_AUTH_MODE_KEY, session.authMode);
  if (session.authMode === "header" && session.adminKey) {
    localStorage.setItem(ADMIN_FALLBACK_KEY, session.adminKey);
  } else {
    localStorage.removeItem(ADMIN_FALLBACK_KEY);
  }
}

export function clearSession(): void {
  localStorage.removeItem(ADMIN_API_URL_KEY);
  localStorage.removeItem(ADMIN_AUTH_MODE_KEY);
  localStorage.removeItem(ADMIN_FALLBACK_KEY);
}

export function isLoggedIn(): boolean {
  const s = getSession();
  return !!s && s.apiUrl.length > 0;
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

export async function createAdminSession(
  apiUrl: string,
  login: string,
  password: string,
): Promise<void> {
  const base = normalizeApiUrl(apiUrl);
  const response = await fetch(`${base}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login, password }),
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  saveSession({ apiUrl: base, authMode: "cookie" });
}

export async function createHeaderSession(apiUrl: string, adminKey: string): Promise<void> {
  const base = normalizeApiUrl(apiUrl);
  const response = await fetch(`${base}/admin/health`, {
    method: "GET",
    headers: {
      "x-admin-key": adminKey,
    },
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  saveSession({ apiUrl: base, authMode: "header", adminKey });
}

export async function ensureAdminSession(sessionOrApiUrl: AdminSession | string): Promise<void> {
  if (typeof sessionOrApiUrl === "string") {
    const base = normalizeApiUrl(sessionOrApiUrl);
    const response = await fetch(`${base}/admin/session`, {
      method: "GET",
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    return;
  }

  const session = sessionOrApiUrl;
  const base = normalizeApiUrl(session.apiUrl);
  if (session.authMode === "header") {
    if (!session.adminKey) {
      throw new Error("Missing admin key for header mode");
    }
    const response = await fetch(`${base}/admin/health`, {
      method: "GET",
      headers: {
        "x-admin-key": session.adminKey,
      },
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    return;
  }

  const response = await fetch(`${base}/admin/session`, {
    method: "GET",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
}

export async function revokeAdminSession(sessionOrApiUrl: AdminSession | string): Promise<void> {
  if (typeof sessionOrApiUrl === "string") {
    const base = normalizeApiUrl(sessionOrApiUrl);
    await fetch(`${base}/admin/session`, {
      method: "DELETE",
      credentials: "include",
    });
    return;
  }

  if (sessionOrApiUrl.authMode === "cookie") {
    const base = normalizeApiUrl(sessionOrApiUrl.apiUrl);
    await fetch(`${base}/admin/session`, {
      method: "DELETE",
      credentials: "include",
    });
  }
}

/** Helper - makes a fetch call to /admin/* with cookie or header-backed session. */
export async function adminFetch(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const session = getSession();
  if (!session) throw new Error("Not authenticated");
  const url = `${normalizeApiUrl(session.apiUrl)}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string> | undefined) ?? {}),
    };
    if (session.authMode === "header" && session.adminKey) {
      headers["x-admin-key"] = session.adminKey;
    }

    return await fetch(url, {
      ...options,
      credentials: session.authMode === "cookie" ? "include" : "omit",
      signal: options.signal ?? controller.signal,
      headers,
    });
  } finally {
    clearTimeout(timeout);
  }
}
