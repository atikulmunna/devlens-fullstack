import { describe, expect, it } from "vitest";

import { forwardResponseHeaders } from "./proxy";

describe("forwardResponseHeaders", () => {
  it("keeps every Set-Cookie header", () => {
    // Login and refresh each set two cookies (refresh + CSRF); dropping one breaks the session.
    const upstream = new Headers();
    upstream.append("set-cookie", "devlens_refresh_token=abc; Path=/; HttpOnly");
    upstream.append("set-cookie", "devlens_csrf_token=xyz; Path=/");

    expect(forwardResponseHeaders(upstream).getSetCookie()).toEqual([
      "devlens_refresh_token=abc; Path=/; HttpOnly",
      "devlens_csrf_token=xyz; Path=/"
    ]);
  });

  it("drops hop-by-hop headers and keeps the rest", () => {
    const upstream = new Headers({
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
      "transfer-encoding": "chunked",
      "content-length": "42"
    });

    const forwarded = forwardResponseHeaders(upstream);

    expect(forwarded.get("content-type")).toBe("text/event-stream");
    expect(forwarded.get("cache-control")).toBe("no-cache");
    expect(forwarded.has("connection")).toBe(false);
    expect(forwarded.has("transfer-encoding")).toBe(false);
    expect(forwarded.has("content-length")).toBe(false);
  });
});
