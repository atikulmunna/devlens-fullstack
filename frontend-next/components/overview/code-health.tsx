"use client";

import { useState } from "react";
import type { TechDebtFlags } from "@/lib/api";
import { plural } from "@/lib/format";
import { githubFileUrl } from "@/lib/github-links";

const FIRST_ROWS = 8;

type Props = { debt: TechDebtFlags | null; githubUrl: string; commitSha: string | null | undefined };

// Facts, not a score: which functions are long (each linked to its lines on GitHub at the analyzed
// commit), how many notes are left, whether tests exist.
export function CodeHealth({ debt, githubUrl, commitSha }: Props) {
  const [showAll, setShowAll] = useState(false);
  if (!debt?.measured) {
    return <p className="muted">This analysis predates code health checks. Analyze the repository again to see them.</p>;
  }
  const longFunctions = debt.long_functions ?? [];
  const longCount = debt.long_function_count ?? 0;
  const todoCount = debt.todo_count ?? 0;
  const testFiles = debt.test_file_count ?? 0;
  const rows = showAll ? longFunctions : longFunctions.slice(0, FIRST_ROWS);

  return (
    <div className="health">
      <ul className="health-facts">
        <li>
          {longCount === 0
            ? `No functions over ${debt.long_function_lines} lines.`
            : `${plural(longCount, "function")} over ${debt.long_function_lines} lines, longest first.`}
        </li>
        <li>
          {todoCount === 0
            ? "No TODO or FIXME notes in the code."
            : `${plural(todoCount, "TODO or FIXME note")} in ${plural(debt.todo_file_count ?? 0, "file")}.`}
        </li>
        <li>{testFiles === 0 ? "No test files found." : `${plural(testFiles, "test file")}.`}</li>
      </ul>
      {rows.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Function</th>
              <th scope="col">Where</th>
              <th scope="col" className="numeric">
                Lines
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((fn) => (
              <tr key={`${fn.file}:${fn.line}`}>
                <td className="mono">{fn.name}</td>
                <td className="mono">
                  <a href={githubFileUrl(githubUrl, commitSha, fn.file, { start: fn.line, end: fn.line + fn.length - 1 })} rel="noreferrer">
                    {fn.file}:{fn.line}
                  </a>
                </td>
                <td className="numeric">{fn.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {longFunctions.length > FIRST_ROWS && (
        <button type="button" className="link-button" onClick={() => setShowAll((value) => !value)}>
          {showAll ? "Show fewer" : `Show all ${longFunctions.length}`}
        </button>
      )}
    </div>
  );
}
