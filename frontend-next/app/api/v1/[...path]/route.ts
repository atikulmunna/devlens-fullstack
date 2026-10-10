import { NextRequest } from "next/server";
import { getBackendBase } from "@/lib/api";
import { forwardResponseHeaders, HOP_BY_HOP_HEADERS } from "@/lib/proxy";

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const upstreamUrl = new URL(`${getBackendBase()}/api/v1/${path.join("/")}`);
  upstreamUrl.search = request.nextUrl.search;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
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
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: forwardResponseHeaders(upstream.headers)
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
