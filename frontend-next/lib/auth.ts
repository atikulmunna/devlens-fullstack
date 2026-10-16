import type { components } from "./api-schema";

// Session handling for the GitHub-backed auth flow.
//
// The access token lives in memory only. A reload restores it from the HttpOnly refresh cookie via
// /auth/refresh, so no long-lived credential sits in localStorage where injected script could read it.

export type CurrentUser = components["schemas"]["CurrentUserResponse"];

const CSRF_COOKIE = "devlens_csrf_token";

let accessToken = "";
let refreshInFlight: Promise<string> | null = null;

function readCookie(name: string): string {
  if (typeof document === "undefined") {
    return "";
  }
  const match = document.cookie.split("; ").find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

function csrfHeaders(): Record<string, string> {
  const csrf = readCookie(CSRF_COOKIE);
  return csrf ? { "X-CSRF-Token": csrf } : {};
}

async function requestRefresh(): Promise<string> {
  const response = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: csrfHeaders(),
    cache: "no-store"
  });
  const payload = response.ok ? await response.json().catch(() => null) : null;
  accessToken = payload?.access_token || "";
  if (!accessToken) {
    throw new Error("Not signed in");
  }
  return accessToken;
}

export function refreshAccessToken(): Promise<string> {
  // The refresh cookie rotates on every use, so two concurrent refreshes would spend the same
  // cookie twice and the server would revoke the second, signing the user out. Share one call.
  if (!refreshInFlight) {
    refreshInFlight = requestRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function withToken(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return { ...init, headers, cache: "no-store" };
}

// fetch with the access token attached; on a 401 it refreshes once and retries. Request bodies
// must be resendable (strings), which holds for every JSON call in this app.
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(input, withToken(init));
  if (response.status !== 401) {
    return response;
  }
  try {
    await refreshAccessToken();
  } catch {
    return response;
  }
  return fetch(input, withToken(init));
}

export async function loadCurrentUser(): Promise<CurrentUser | null> {
  const response = await authFetch("/api/v1/auth/me");
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as CurrentUser;
}

export async function signOut(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "DELETE",
      credentials: "include",
      headers: csrfHeaders(),
      cache: "no-store"
    });
  } finally {
    // Forget the session locally even if the server call fails.
    accessToken = "";
  }
}

export function signInHref(nextPath: string): string {
  return `/api/v1/auth/github?next=${encodeURIComponent(nextPath)}`;
}
