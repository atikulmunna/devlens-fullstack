import { timingSafeEqual } from "node:crypto";

// Caddy (deploy/Caddyfile) lets a request through when this cookie holds DEVLENS_GATE_SECRET.
export const ACCESS_COOKIE = "devlens_access";
const MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

// Constant time, so the comparison does not reveal how much of a guess was right.
export function keyMatches(given: unknown, secret: string | undefined): boolean {
  if (!secret || typeof given !== "string") {
    return false;
  }
  const a = Buffer.from(given.trim());
  const b = Buffer.from(secret);
  return a.length === b.length && timingSafeEqual(a, b);
}

// The access page posts its key here instead of putting it in the URL, where it would land in
// proxy logs and browser history. 303 makes the browser follow with a GET, not a second POST.
export function gateResponse(given: unknown, secret: string | undefined): Response {
  const headers = new Headers({ "Cache-Control": "no-store" });
  if (!keyMatches(given, secret)) {
    headers.set("Location", "/?denied=1");
    return new Response(null, { status: 303, headers });
  }
  headers.set("Location", "/");
  headers.set("Set-Cookie", `${ACCESS_COOKIE}=${secret}; Path=/; Max-Age=${MAX_AGE_SECONDS}; Secure; HttpOnly; SameSite=Lax`);
  return new Response(null, { status: 303, headers });
}

// A body that is not a form counts as a wrong key.
export async function enterGate(request: Request, secret: string | undefined): Promise<Response> {
  const form = await request.formData().catch(() => null);
  return gateResponse(form?.get("key"), secret);
}
