export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
export const API_ORIGIN = API_URL.replace(/\/api(\/v\d+)?\/?$/, "");

const ACCESS_TOKEN_KEY = "petspace.access_token";
const REFRESH_TOKEN_KEY = "petspace.refresh_token";

export const SESSION_EXPIRED_EVENT = "petspace:session-expired";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export function mediaUrl(path?: string | null) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${API_ORIGIN}${path}`;
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(tokens: Pick<TokenPair, "access_token" | "refresh_token">): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function notifySessionExpired(): void {
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    clearTokens();
    notifySessionExpired();
    return false;
  }
  setTokens((await response.json()) as TokenPair);
  return true;
}

/**
 * Запрос с access-токеном. При 401 один раз пробует обновить пару токенов
 * и повторяет запрос: короткий access-токен не должен выкидывать пользователя.
 */
export async function authorizedFetch(path: string, init: RequestInit = {}, allowRetry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  const accessToken = getAccessToken();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${API_URL}${path}`, { ...init, headers });

  const isAuthCall = path.startsWith("/auth/");
  if (response.status === 401 && allowRetry && !isAuthCall && getRefreshToken()) {
    if (await refreshAccessToken()) {
      return authorizedFetch(path, init, false);
    }
  }
  return response;
}

async function errorFrom(response: Response): Promise<ApiError> {
  const text = await response.text();
  let detail: unknown = text;
  let message = text || `HTTP ${response.status}`;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    detail = parsed.detail ?? parsed;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object" && "message" in detail) {
      message = String((detail as { message: unknown }).message);
    }
  } catch {
    // Ответ не JSON: оставляем текст как есть.
  }
  return new ApiError(response.status, message, detail);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authorizedFetch(path, init);
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
