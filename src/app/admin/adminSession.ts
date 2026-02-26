const ADMIN_API_URL_KEY = "gg_admin_api_url";
const REQUEST_TIMEOUT_MS = 12000;

export interface AdminSession {
  apiUrl: string;
}

function normalizeApiUrl(apiUrl: string): string {
  return apiUrl.trim().replace(/\/$/, "");
}

export function getSession(): AdminSession | null {
  try {
    const apiUrl = localStorage.getItem(ADMIN_API_URL_KEY) ?? "";
    if (!apiUrl) return null;
    return { apiUrl };
  } catch {
    return null;
  }
}

export function saveSession(session: AdminSession): void {
  localStorage.setItem(ADMIN_API_URL_KEY, normalizeApiUrl(session.apiUrl));
}

export function clearSession(): void {
  localStorage.removeItem(ADMIN_API_URL_KEY);
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

export async function createAdminSession(apiUrl: string, adminKey: string): Promise<void> {
  const base = normalizeApiUrl(apiUrl);
  const response = await fetch(`${base}/admin/session`, {
    method: "POST",
    headers: {
      "x-admin-key": adminKey,
    },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  saveSession({ apiUrl: base });
}

export async function ensureAdminSession(apiUrl: string): Promise<void> {
  const base = normalizeApiUrl(apiUrl);
  const response = await fetch(`${base}/admin/session`, {
    method: "GET",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
}

export async function revokeAdminSession(apiUrl: string): Promise<void> {
  const base = normalizeApiUrl(apiUrl);
  await fetch(`${base}/admin/session`, {
    method: "DELETE",
    credentials: "include",
  });
}

/** Helper — makes a fetch call to /admin/* with cookie-backed session. */
export async function adminFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const session = getSession();
  if (!session) throw new Error("Not authenticated");
  const url = `${normalizeApiUrl(session.apiUrl)}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, {
      ...options,
      credentials: "include",
      signal: options.signal ?? controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
    });
  } finally {
    clearTimeout(timeout);
  }
}
