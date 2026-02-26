const API_URL = ((import.meta as any).env.VITE_API_URL as string | undefined) ?? "";

function getApiUrl(): string {
  const base = API_URL.trim().replace(/\/$/, "");
  if (!base) {
    throw new Error("Backend not configured. Set VITE_API_URL and rebuild.");
  }
  return base;
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
    const nested = direct && typeof direct.detail === "object" ? (direct.detail as any) : null;

    if (direct?.code && direct?.detail) {
      return {
        ...base,
        code: String(direct.code),
        detail: String(direct.detail),
        userAction: String(direct.user_action ?? base.userAction),
        metadata: (direct.metadata as Record<string, unknown>) ?? undefined,
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

    if (typeof direct?.detail === "string") {
      return { ...base, detail: direct.detail };
    }
    if (typeof direct?.message === "string") {
      return { ...base, detail: direct.message };
    }
  } catch {
    // ignore parse errors
  }
  return base;
}

export async function createGenerationSession(): Promise<void> {
  const response = await fetch(`${getApiUrl()}/auth/session`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    const err = await readApiError(response, "Failed to create generation session.");
    throw new Error(`${err.detail} ${err.userAction}`.trim());
  }
}

export async function ensureGenerationSession(): Promise<void> {
  const response = await fetch(`${getApiUrl()}/auth/session`, {
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
  const url = `${getApiUrl()}${path}`;
  const doFetch = () =>
    fetch(url, {
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
