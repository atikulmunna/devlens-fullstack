import { enterGate } from "@/lib/gate";

// The access page's form target in production (Caddy routes POST /gate/enter here before its gate).
export function POST(request: Request): Promise<Response> {
  return enterGate(request, process.env.DEVLENS_GATE_SECRET);
}
