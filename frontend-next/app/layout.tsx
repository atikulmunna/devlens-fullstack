import type { Metadata } from "next";
import { Atkinson_Hyperlegible, IBM_Plex_Mono } from "next/font/google";
import Link from "next/link";
import { AuthProvider, AuthStatus } from "@/components/auth";
import { FrontendTelemetry } from "@/components/frontend-telemetry";
import "./globals.css";

const atkinson = Atkinson_Hyperlegible({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-atkinson",
  display: "swap"
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap"
});

export const metadata: Metadata = {
  title: "DevLens",
  description: "Understand a GitHub repository before you change it: grounded answers, dependency maps, and commit risk."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${atkinson.variable} ${plexMono.variable}`}>
      <body>
        <AuthProvider>
          <header className="site-header">
            <div className="site-header-inner">
              <Link href="/" className="wordmark">
                DevLens
              </Link>
              <nav className="nav" aria-label="Main">
                <Link href="/analyze">Analyze</Link>
                <Link href="/workspace">Workspace</Link>
                <span className="auth">
                  <AuthStatus />
                </span>
              </nav>
            </div>
          </header>
          <main className="shell">
            <FrontendTelemetry />
            {children}
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
