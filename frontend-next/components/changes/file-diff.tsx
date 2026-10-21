import type { ChangedFile, SecurityFlag } from "@/lib/api";
import { SeverityBadge } from "./severity";

const SIGN: Record<string, string> = { "+": "+", "-": "−", " ": "" };

// One changed file: a summary row that opens to its hunks, with lines that match a security
// pattern marked and labeled. Files with a flag start open.
export function FileDiff({ file, flag }: { file: ChangedFile; flag?: SecurityFlag }) {
  const hunks = file.hunk_details ?? [];
  return (
    <details className="file-diff" open={Boolean(flag)}>
      <summary>
        <span className="mono file-diff-path">{file.path}</span>
        <span className="file-diff-meta">
          <span className="muted">{file.status}</span>
          <span className="added">+{file.added}</span>
          <span className="removed">{"−"}{file.removed}</span>
          {flag && <SeverityBadge level={flag.severity} />}
        </span>
      </summary>
      {hunks.length === 0 ? (
        <p className="muted file-diff-note">
          {file.hunks > 0
            ? "Line detail was not captured for this commit. Analyze the repository again to see it."
            : "No text changes to show (for example a binary file or a rename)."}
        </p>
      ) : (
        <div className="hunks">
          {hunks.map((hunk, index) => (
            <table key={index} className="hunk">
              <tbody>
                {hunk.lines?.map((line, lineIndex) => {
                  const kind = line.kind === "+" ? "added" : line.kind === "-" ? "removed" : "context";
                  const flagged = (line.labels ?? []).length > 0;
                  return (
                    <tr key={lineIndex} className={`line-${kind}${flagged ? " flagged" : ""}`}>
                      <td className="line-no">{line.old ?? ""}</td>
                      <td className="line-no">{line.new ?? ""}</td>
                      <td className="line-sign">{SIGN[line.kind]}</td>
                      <td className="line-text">
                        <code>{line.text}</code>
                        {flagged && <span className="line-labels">{line.labels?.join(", ")}</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ))}
          {file.truncated && <p className="muted file-diff-note">Some lines are left out to keep large commits readable.</p>}
        </div>
      )}
    </details>
  );
}
