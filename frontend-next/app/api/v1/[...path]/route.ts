import { NextRequest } from "next/server";
import { getBackendBase } from "@/lib/api";

const hopByHopHeaders = new Set([
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

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const upstreamUrl = new URL(`${getBackendBase()}/api/v1/${path.join("/")}`);
  upstreamUrl.search = request.nextUrl.search;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (!hopByHopHeaders.has(lower)) {
      headers.set(key, value);
    }
  });

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual"
  };
  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(upstreamUrl.toString(), init);
  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (!hopByHopHeaders.has(lower)) {
      responseHeaders.set(key, value);
    }
  });
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders
  });
}

type Ctx = { params: { path: string[] } };

export async function GET(request: NextRequest, context: Ctx): Promise<Response> {
  return proxy(request, context.params.path);
}

export async function POST(request: NextRequest, context: Ctx): Promise<Response> {
  return proxy(request, context.params.path);
}

export async function PUT(request: NextRequest, context: Ctx): Promise<Response> {
  return proxy(request, context.params.path);
}

export async function PATCH(request: NextRequest, context: Ctx): Promise<Response> {
  return proxy(request, context.params.path);
}

export async function DELETE(request: NextRequest, context: Ctx): Promise<Response> {
  return proxy(request, context.params.path);
}

export async function OPTIONS(request: NextRequest, context: Ctx): Promise<Response> {
  return proxy(request, context.params.path);
}
