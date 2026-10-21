import type { Metadata } from "next";
import { Atkinson_Hyperlegible, IBM_Plex_Mono } from "next/font/google";
import Link from "next/link";
import { AuthProvider, AuthStatus } from "@/components/auth";
import { FrontendTelemetry } from "@/components/frontend-telemetry";
import { LogoMark } from "@/components/logo-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { THEME_SCRIPT } from "@/lib/theme";
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
    // The head script sets data-theme before React loads, so the server markup differs on purpose.
    <html lang="en" className={`${atkinson.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <AuthProvider>
          <header className="site-header">
            <div className="site-header-inner">
              <Link href="/" className="wordmark">
                <LogoMark />
                DevLens
              </Link>
              <nav className="nav" aria-label="Main">
                <span className="auth">
                  <AuthStatus />
                </span>
                <ThemeToggle />
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
