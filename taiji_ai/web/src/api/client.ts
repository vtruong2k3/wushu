import type { ApiErrorBody } from "./types";

/** Error raised for any failed API call. `code` comes from the backend error format when available. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(code: string, message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const err = (value as { error: unknown }).error;
  return typeof err === "object" && err !== null && typeof (err as { code?: unknown }).code === "string";
}

/** GET a JSON resource under /api. Same origin in production (served by FastAPI), proxied by Vite in dev. */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error(`apiGet expects an /api/ path, got ${path}`);
  // `new Headers()` accepts every HeadersInit form (object, array, Headers) — object spread does not (BUG-0005).
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (err) {
    // Cancellation (react-query abort on unmount/refetch) is not a connectivity problem: propagate it unchanged.
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("network_error", "Không kết nối được tới máy chủ API", null);
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // non-JSON error body (proxy error page, etc.)
    }
    if (isApiErrorBody(body)) throw new ApiError(body.error.code, body.error.message, response.status);
    throw new ApiError("http_error", `HTTP ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}
