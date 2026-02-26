const API_URL = ((import.meta as any).env.VITE_API_URL as string | undefined) ?? "";

function getApiUrl(): string {
  const base = API_URL.trim().replace(/\/$/, "");
  if (!base) {
    throw new Error("Backend not configured. Set VITE_API_URL and rebuild.");
  }
  return base;
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json();
    if (payload?.detail?.detail) return payload.detail.detail as string;
    if (typeof payload?.detail === "string") return payload.detail;
    if (typeof payload?.message === "string") return payload.message;
  } catch {
    // ignore parse errors
  }
  return fallback;
}

export async function createGenerationSession(): Promise<void> {
  const response = await fetch(`${getApiUrl()}/auth/session`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await readErrorMessage(response, "Failed to create generation session.");
    throw new Error(detail);
  }
}

export async function ensureGenerationSession(): Promise<void> {
  const response = await fetch(`${getApiUrl()}/auth/session`, {
    method: "GET",
    credentials: "include",
  });
  if (response.ok) return;
  if (response.status !== 401) {
    const detail = await readErrorMessage(response, "Failed to check generation session.");
    throw new Error(detail);
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

