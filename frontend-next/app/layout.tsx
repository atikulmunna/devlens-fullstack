import type { Metadata } from "next";
import Link from "next/link";
import { AuthProvider, AuthStatus } from "@/components/auth";
import { FrontendTelemetry } from "@/components/frontend-telemetry";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevLens",
  description: "Repository intelligence: analyze, explore, and chat over indexed code with citations."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <main className="shell">
            <span className="chip">DevLens</span>
            <h1 className="title">DevLens</h1>
            <p className="subtitle">
              Analyze any public GitHub repository and chat with citation-grounded answers over its code.
            </p>
            <nav className="nav">
              <Link href="/">Home</Link>
              <Link href="/analyze">Analyze</Link>
              <Link href="/workspace">Workspace</Link>
              <span className="auth">
                <AuthStatus />
              </span>
            </nav>
            <FrontendTelemetry />
            {children}
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
