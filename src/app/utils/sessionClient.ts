const API_URL = ((import.meta as any).env.VITE_API_URL as string | undefined) ?? "";

function normalizeBase(value: string): string {
  return value.trim().replace(/\/$/, "");
}

function getApiBases(): string[] {
  const bases: string[] = ["/api"];
  const envBase = normalizeBase(API_URL);
  if (envBase && !bases.includes(envBase)) {
    bases.push(envBase);
  }
  return bases;
}

function buildUrl(base: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!base) return normalizedPath;
  if (base.startsWith("http://") || base.startsWith("https://")) {
    return `${base}${normalizedPath}`;
  }
  return `${base}${normalizedPath}`;
}

export interface ApiErrorPayload {
  status: number;
  code: string;
  detail: string;
  userAction: string;
  metadata?: Record<string, unknown>;
}

export async function readApiError(response: Response, fallback: string): Promise<ApiErrorPayload> {
  const base: ApiErrorPayload = {
    status: response.status,
    code: "request_failed",
    detail: fallback,
    userAction: "Retry later.",
  };
  try {
    const payload = await response.json();
    const direct = payload && typeof payload === "object" ? payload : null;
    const nested = direct && typeof (direct as any).detail === "object" ? ((direct as any).detail as any) : null;

    if ((direct as any)?.code && (direct as any)?.detail) {
      return {
        ...base,
        code: String((direct as any).code),
        detail: String((direct as any).detail),
        userAction: String((direct as any).user_action ?? base.userAction),
        metadata: ((direct as any).metadata as Record<string, unknown>) ?? undefined,
      };
    }

    if (nested?.code && nested?.detail) {
      return {
        ...base,
        code: String(nested.code),
        detail: String(nested.detail),
        userAction: String(nested.user_action ?? base.userAction),
        metadata: (nested.metadata as Record<string, unknown>) ?? undefined,
      };
    }

    if (typeof (direct as any)?.detail === "string") {
      return { ...base, detail: (direct as any).detail };
    }
    if (typeof (direct as any)?.message === "string") {
      return { ...base, detail: (direct as any).message };
    }
  } catch {
    // Ignore parse errors.
  }
  return base;
}

async function fetchWithFallback(path: string, init: RequestInit): Promise<Response> {
  const bases = getApiBases();
  let lastError: unknown = null;

  for (let index = 0; index < bases.length; index += 1) {
    const base = bases[index];
    const url = buildUrl(base, path);
    try {
      const response = await fetch(url, init);
      // If /api is unavailable in local dev (404/502), fallback to env URL.
      const canFallback = index < bases.length - 1;
      if (
        canFallback &&
        base === "/api" &&
        (response.status === 404 || response.status === 502 || response.status === 503)
      ) {
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
  throw new Error("Failed to reach generation API");
}

export async function createGenerationSession(): Promise<void> {
  const response = await fetchWithFallback("/auth/session", {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    const err = await readApiError(response, "Failed to create generation session.");
    throw new Error(`${err.detail} ${err.userAction}`.trim());
  }
}

export async function ensureGenerationSession(): Promise<void> {
  const response = await fetchWithFallback("/auth/session", {
    method: "GET",
    credentials: "include",
  });
  if (response.ok) return;
  if (response.status !== 401) {
    const err = await readApiError(response, "Failed to check generation session.");
    throw new Error(`${err.detail} ${err.userAction}`.trim());
  }
  await createGenerationSession();
}

interface SessionFetchOptions {
  retryOn401?: boolean;
}

export async function sessionFetch(
  path: string,
  options: RequestInit = {},
  sessionOptions: SessionFetchOptions = {},
): Promise<Response> {
  const doFetch = () =>
    fetchWithFallback(path, {
      ...options,
      credentials: "include",
      headers: {
        ...(options.headers ?? {}),
      },
    });

  let response = await doFetch();
  if (response.status === 401 && sessionOptions.retryOn401) {
    await createGenerationSession();
    response = await doFetch();
  }
  return response;
}

export function resolveMediaUrl(
  rawUrl: string | null | undefined,
  fallbackPath: string,
): string {
  const fallback = fallbackPath.startsWith("/api/") ? fallbackPath : buildUrl("/api", fallbackPath);
  if (!rawUrl) return fallback;

  const rewritePath = (pathname: string, search: string): string => {
    if (pathname.startsWith("/results/") || pathname.startsWith("/preview/")) {
      return `/api${pathname}${search}`;
    }
    return "";
  };

  if (rawUrl.startsWith("/")) {
    const rewritten = rewritePath(rawUrl, "");
    return rewritten || rawUrl;
  }

  try {
    const parsed = new URL(rawUrl);
    const rewritten = rewritePath(parsed.pathname, parsed.search);
    if (!rewritten) {
      return rawUrl;
    }

    if (parsed.origin === window.location.origin) {
      return rewritten;
    }

    return rawUrl;
  } catch {
    return fallback;
  }
}
