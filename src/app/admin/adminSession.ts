/**
 * Admin Session — stores credentials in sessionStorage (cleared on tab close).
 * Never hardcoded into env vars or baked into Docker image.
 */

const SESSION_KEY = "gg_admin_session";

export interface AdminSession {
  apiUrl: string;   // e.g. https://xxxx--gooni-gooni-backend.modal.run
  adminKey: string; // the ADMIN_KEY secret
}

export function getSession(): AdminSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AdminSession;
  } catch {
    return null;
  }
}

export function saveSession(session: AdminSession): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

export function isLoggedIn(): boolean {
  const s = getSession();
  return !!s && s.apiUrl.length > 0 && s.adminKey.length > 0;
}

/** Helper — makes a fetch call to /admin/* with the stored session. */
export async function adminFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const session = getSession();
  if (!session) throw new Error("Not authenticated");
  const url = `${session.apiUrl.replace(/\/$/, "")}${path}`;
  return fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "x-admin-key": session.adminKey,
      ...(options.headers ?? {}),
    },
  });
}
