import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type AuthModule = typeof import("./auth");

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function header(init: unknown, name: string): string | null {
  return new Headers((init as RequestInit | undefined)?.headers).get(name);
}

describe("auth session", () => {
  let auth: AuthModule;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    // Fresh module per test: the token and in-flight refresh are module state.
    vi.resetModules();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("document", { cookie: "devlens_csrf_token=csrf-123" });
    auth = await import("./auth");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("refreshes once on a 401 and retries with the new token", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "fresh" }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    const response = await auth.authFetch("/api/v1/chat/sessions", { method: "POST", body: "{}" });

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/chat/sessions",
      "/api/v1/auth/refresh",
      "/api/v1/chat/sessions"
    ]);
    expect(header(fetchMock.mock.calls[0][1], "Authorization")).toBeNull();
    expect(header(fetchMock.mock.calls[1][1], "X-CSRF-Token")).toBe("csrf-123");
    expect(fetchMock.mock.calls[1][1].credentials).toBe("include");
    expect(header(fetchMock.mock.calls[2][1], "Authorization")).toBe("Bearer fresh");
    expect(fetchMock.mock.calls[2][1].body).toBe("{}");
  });

  it("returns the original 401 without looping when the refresh fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, {})).mockResolvedValueOnce(jsonResponse(401, {}));

    const response = await auth.authFetch("/api/v1/auth/me");

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shares one refresh between concurrent 401s", async () => {
    // The refresh cookie rotates on use: a second concurrent refresh would be revoked server-side.
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/auth/refresh") {
        await new Promise((resolve) => setTimeout(resolve, 10));
        return jsonResponse(200, { access_token: "shared" });
      }
      return jsonResponse(header(init, "Authorization") === "Bearer shared" ? 200 : 401, {});
    });

    const [first, second] = await Promise.all([auth.authFetch("/api/v1/a"), auth.authFetch("/api/v1/b")]);

    expect([first.status, second.status]).toEqual([200, 200]);
    expect(fetchMock.mock.calls.filter((call) => call[0] === "/api/v1/auth/refresh")).toHaveLength(1);
  });

  it("signs out on the server with the CSRF header", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await auth.signOut();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/auth/logout");
    expect(init.method).toBe("DELETE");
    expect(init.credentials).toBe("include");
    expect(header(init, "X-CSRF-Token")).toBe("csrf-123");
  });

  it("forgets the token even when the sign-out call fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { access_token: "t1" }));
    await auth.refreshAccessToken();
    fetchMock.mockRejectedValueOnce(new TypeError("network down"));

    await expect(auth.signOut()).rejects.toThrow("network down");

    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));
    await auth.authFetch("/api/v1/x");
    expect(header(fetchMock.mock.calls[2][1], "Authorization")).toBeNull();
  });

  it("reports no current user when signed out", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, {})).mockResolvedValueOnce(jsonResponse(401, {}));

    await expect(auth.loadCurrentUser()).resolves.toBeNull();
  });

  it("builds a sign-in link that returns to the current page", () => {
    expect(auth.signInHref("/workspace?repo=abc")).toBe("/api/v1/auth/github?next=%2Fworkspace%3Frepo%3Dabc");
  });
});
