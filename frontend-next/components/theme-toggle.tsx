"use client";

import { useEffect, useState } from "react";
import { browserStorage, saveTheme, Theme } from "@/lib/theme";

// Light by default; this switches to the dark map and remembers the choice in this browser.
// The <head> script in app/layout.tsx applies a saved choice before the page paints.
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    if (next === "dark") {
      document.documentElement.dataset.theme = "dark";
    } else {
      delete document.documentElement.dataset.theme;
    }
    saveTheme(browserStorage(), next);
    setTheme(next);
  }

  const dark = theme === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="Dark theme"
      aria-pressed={dark}
      title={dark ? "Switch to the light theme" : "Switch to the dark theme"}
      onClick={toggle}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        {dark ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
          </>
        ) : (
          <path d="M20 14.6A8 8 0 0 1 9.4 4a8 8 0 1 0 10.6 10.6Z" />
        )}
      </svg>
    </button>
  );
}
