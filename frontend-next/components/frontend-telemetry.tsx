"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

type Payload = {
  event: string;
  route?: string;
  duration_ms?: number;
  message?: string;
  metadata?: Record<string, unknown>;
};

function send(payload: Payload): void {
  void fetch("/api/internal/frontend-telemetry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true
  });
}

export function FrontendTelemetry(): null {
  const pathname = usePathname();
  const routeStart = useRef<number>(performance.now());

  useEffect(() => {
    routeStart.current = performance.now();
  }, [pathname]);

  useEffect(() => {
    const duration = performance.now() - routeStart.current;
    send({
      event: "route_load",
      route: pathname,
      duration_ms: Number(duration.toFixed(2))
    });
  }, [pathname]);

  useEffect(() => {
    function onError(event: ErrorEvent): void {
      send({
        event: "client_error",
        route: window.location.pathname,
        message: event.message
      });
    }
    function onRejection(event: PromiseRejectionEvent): void {
      send({
        event: "unhandled_rejection",
        route: window.location.pathname,
        message: String(event.reason ?? "unknown rejection")
      });
    }
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
