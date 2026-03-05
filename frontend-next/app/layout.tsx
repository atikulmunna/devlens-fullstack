import type { Metadata } from "next";
import Link from "next/link";
import { FrontendTelemetry } from "@/components/frontend-telemetry";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevLens Next Foundation",
  description: "Parallel Next.js + TypeScript frontend foundation for DevLens."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main className="shell">
          <span className="chip">DevLens Next scaffold</span>
          <h1 className="title">DevLens Frontend Migration</h1>
          <p className="subtitle">
            Parallel Next.js + TypeScript foundation while legacy frontend remains active.
          </p>
          <nav className="nav">
            <Link href="/">Home</Link>
            <Link href="/analyze">Analyze</Link>
            <Link href="/dashboard/demo-repo-id">Dashboard</Link>
          </nav>
          <FrontendTelemetry />
          {children}
        </main>
      </body>
    </html>
  );
}
