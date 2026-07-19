// Liveness endpoint for docker-compose / Railway healthchecks.
export function GET(): Response {
  return new Response("ok", { status: 200 });
}
