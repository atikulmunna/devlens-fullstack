"use client";

import { useState } from "react";
import type { LanguageShare } from "@/lib/api";

// Fixed categorical order (CSS tokens, stepped separately for light and dark in globals.css).
// Assigned by rank, so the largest language is always green.
const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)"];
const OTHER = "var(--series-other)";

type Segment = { name: string; percent: number; color: string };

function percentLabel(percent: number): string {
  return percent < 1 ? "under 1%" : `${Math.round(percent)}%`;
}

// Code languages as one bar (shares of the code), with docs and config listed beside it.
function codeSegments(languages: LanguageShare[]): Segment[] {
  const code = languages.filter((language) => language.is_code);
  const total = code.reduce((sum, language) => sum + language.share, 0);
  if (total <= 0) {
    return [];
  }
  const named = code.slice(0, SERIES.length).map((language, index) => ({
    name: language.name,
    percent: (language.share / total) * 100,
    color: SERIES[index],
  }));
  const rest = code.slice(SERIES.length).reduce((sum, language) => sum + language.share, 0);
  return rest > 0 ? [...named, { name: "Other", percent: (rest / total) * 100, color: OTHER }] : named;
}

export function LanguageBar({ languages }: { languages: LanguageShare[] }) {
  const [active, setActive] = useState<string | null>(null);
  const segments = codeSegments(languages);
  const docs = languages.filter((language) => !language.is_code);

  if (segments.length === 0) {
    return <p className="muted">No code languages were indexed.</p>;
  }
  return (
    <div className="languages">
      <div className="language-bar" role="img" aria-label={segments.map((s) => `${s.name} ${percentLabel(s.percent)}`).join(", ")}>
        {segments.map((segment) => (
          <span
            key={segment.name}
            className={active && active !== segment.name ? "language-segment dimmed" : "language-segment"}
            style={{ flexGrow: segment.percent, background: segment.color }}
            title={`${segment.name}: ${percentLabel(segment.percent)} of the code`}
            onMouseEnter={() => setActive(segment.name)}
            onMouseLeave={() => setActive(null)}
          />
        ))}
      </div>
      <ul className="language-legend">
        {segments.map((segment) => (
          <li
            key={segment.name}
            className={active === segment.name ? "active" : undefined}
            onMouseEnter={() => setActive(segment.name)}
            onMouseLeave={() => setActive(null)}
          >
            <span className="swatch" style={{ background: segment.color }} aria-hidden="true" />
            {segment.name} <span className="muted">{percentLabel(segment.percent)}</span>
          </li>
        ))}
      </ul>
      {docs.length > 0 && (
        <p className="muted language-docs">
          Docs and config, as a share of everything indexed:{" "}
          {docs.map((language) => `${language.name} ${percentLabel(language.share)}`).join(", ")}.
        </p>
      )}
    </div>
  );
}
