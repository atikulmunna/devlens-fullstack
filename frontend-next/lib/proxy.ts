// Header handling for the /api/v1 proxy route (route files may only export HTTP handlers).

export const HOP_BY_HOP_HEADERS = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-length"
]);

// Copy upstream response headers for the browser, dropping hop-by-hop ones. Iteration yields each
// Set-Cookie separately, so append (set would keep only the last cookie and break the session).
export function forwardResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  upstream.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.append(key, value);
    }
  });
  return headers;
}
