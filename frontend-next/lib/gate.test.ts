import { describe, expect, it } from "vitest";

import { enterGate, gateResponse, keyMatches } from "./gate";

const SECRET = "3f9a1c0be47d2265a8c91e0f";

function post(body: string | null, contentType = "application/x-www-form-urlencoded") {
  return new Request("http://localhost/gate/enter", { method: "POST", body, headers: { "Content-Type": contentType } });
}

describe("keyMatches", () => {
  it("accepts the exact key, ignoring stray whitespace from a paste", () => {
    expect(keyMatches(SECRET, SECRET)).toBe(true);
    expect(keyMatches(` ${SECRET}\n`, SECRET)).toBe(true);
  });

  it("refuses a wrong, shorter, or missing key, and refuses everything without a configured secret", () => {
    expect(keyMatches(SECRET.replace("3", "4"), SECRET)).toBe(false);
    expect(keyMatches(SECRET.slice(0, -1), SECRET)).toBe(false);
    expect(keyMatches(null, SECRET)).toBe(false);
    expect(keyMatches("", "")).toBe(false);
    expect(keyMatches(SECRET, undefined)).toBe(false);
  });
});

describe("gateResponse", () => {
  it("sets the access cookie and goes home for the right key", () => {
    const response = gateResponse(SECRET, SECRET);
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/");
    expect(response.headers.get("Set-Cookie")).toBe(
      `devlens_access=${SECRET}; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Lax`
    );
  });

  it("sends a wrong key back to the access page without a cookie", () => {
    const response = gateResponse("guess", SECRET);
    expect(response.headers.get("Location")).toBe("/?denied=1");
    expect(response.headers.get("Set-Cookie")).toBeNull();
  });
});

describe("enterGate", () => {
  it("reads the key from the form body", async () => {
    expect((await enterGate(post(`key=${SECRET}`), SECRET)).headers.get("Location")).toBe("/");
    expect((await enterGate(post("key=nope"), SECRET)).headers.get("Location")).toBe("/?denied=1");
  });

  it("treats a body that is not a form as a wrong key", async () => {
    expect((await enterGate(post("{}", "application/json"), SECRET)).headers.get("Location")).toBe("/?denied=1");
  });
});
