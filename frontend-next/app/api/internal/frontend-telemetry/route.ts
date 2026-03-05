import { NextRequest } from "next/server";

type TelemetryPayload = {
  event: string;
  route?: string;
  duration_ms?: number;
  message?: string;
  metadata?: Record<string, unknown>;
};

export async function POST(request: NextRequest): Promise<Response> {
  let payload: TelemetryPayload | null = null;
  try {
    payload = (await request.json()) as TelemetryPayload;
  } catch {
    return new Response(null, { status: 400 });
  }
  const safe = {
    event: payload?.event || "unknown",
    route: payload?.route || "",
    duration_ms: typeof payload?.duration_ms === "number" ? payload.duration_ms : undefined,
    message: payload?.message || "",
    metadata: payload?.metadata || {}
  };
  console.log("[frontend-next-telemetry]", JSON.stringify(safe));
  return new Response(null, { status: 204 });
}
