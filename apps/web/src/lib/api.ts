// In Docker, API_BASE_URL points to the container-internal URL for SSR;
// browsers fall back to the NEXT_PUBLIC_ value baked in at build time.
export const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NEXT_PUBLIC_API_URL
    ? `${process.env.NEXT_PUBLIC_API_URL}/api`
    : 'http://localhost:8000/api');

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface FetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  accessToken?: string;
}

/**
 * Extracts a user-facing message from any backend error body: FastAPI's
 * `{ detail: string }`, its validation list `{ detail: [{ msg }] }`, and the
 * app's `{ error: { message } }` envelope.
 */
export function errorMessageFromBody(body: unknown): string | null {
  const b = (body ?? {}) as {
    detail?: unknown;
    message?: unknown;
    error?: { message?: unknown };
  };
  if (typeof b.detail === 'string' && b.detail) return b.detail;
  if (Array.isArray(b.detail)) {
    const msgs = b.detail
      .map((d) => (d && typeof d === 'object' ? (d as { msg?: unknown }).msg : undefined))
      .filter((m): m is string => typeof m === 'string' && m.length > 0);
    if (msgs.length > 0) return msgs.join('; ');
  }
  if (typeof b.error?.message === 'string' && b.error.message) return b.error.message;
  if (typeof b.message === 'string' && b.message) return b.message;
  return null;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 429) {
    throw new ApiError(429, 'Troppe richieste — riprova tra qualche secondo');
  }
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      errorMessageFromBody(errorBody) ?? `Request failed (${response.status})`,
      errorBody
    );
  }
  return response.json();
}

export async function apiFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { body, accessToken, headers: customHeaders, ...rest } = options;

  const headers: Record<string, string> = {
    ...(customHeaders as Record<string, string>),
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  if (body !== undefined && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...rest,
    headers,
    body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  return handleResponse<T>(response);
}
