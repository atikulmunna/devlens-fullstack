import type { SecurityFlag } from "@/lib/api";

const LABELS: Record<SecurityFlag["severity"], string> = { high: "High", medium: "Medium", low: "Low" };

// Shape and word as well as color, so severity never rests on color alone.
function Icon({ level }: { level: SecurityFlag["severity"] }) {
  if (level === "high") {
    return <path d="M6 1 L11 10.5 L1 10.5 Z" />;
  }
  if (level === "medium") {
    return <path d="M6 1 L11 6 L6 11 L1 6 Z" />;
  }
  return <circle cx="6" cy="6" r="4" />;
}

export function SeverityBadge({ level }: { level: SecurityFlag["severity"] }) {
  return (
    <span className={`severity severity-${level}`}>
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
        <Icon level={level} />
      </svg>
      {LABELS[level]}
    </span>
  );
}

export const SEVERITY_ORDER: Record<SecurityFlag["severity"], number> = { high: 0, medium: 1, low: 2 };
