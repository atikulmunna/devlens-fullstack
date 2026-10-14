"use client";

import { useEffect, useState } from "react";
import { useRepo } from "@/components/repo-context";
import { DashboardAnalysis, getDashboard, TechDebtFlags } from "@/lib/api";
import { plural } from "@/lib/format";

const LISTED_LONG_FUNCTIONS = 5;

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

// Facts, not a score: which functions are long, how many notes are left, whether tests exist.
function CodeHealth({ debt }: { debt: TechDebtFlags | null }) {
  if (!debt?.measured) {
    return <p className="muted">This analysis predates code health checks. Analyze the repository again to see them.</p>;
  }
  const longFunctions = debt.long_functions ?? [];
  const longCount = debt.long_function_count ?? 0;
  const todoCount = debt.todo_count ?? 0;
  const testFiles = debt.test_file_count ?? 0;
  return (
    <ul className="health">
      <li>
        {longCount === 0
          ? `No functions over ${debt.long_function_lines} lines.`
          : `${plural(longCount, "function")} over ${debt.long_function_lines} lines.`}
        {longFunctions.length > 0 && (
          <ul className="long-functions">
            {longFunctions.slice(0, LISTED_LONG_FUNCTIONS).map((fn) => (
              <li key={`${fn.file}:${fn.line}`}>
                <span className="mono">{fn.name}</span>
                <span className="mono muted">
                  {fn.file}:{fn.line}
                </span>
                <span className="muted">{fn.length} lines</span>
              </li>
            ))}
          </ul>
        )}
        {longCount > LISTED_LONG_FUNCTIONS && (
          <p className="muted">And {(longCount - LISTED_LONG_FUNCTIONS).toLocaleString("en-US")} more.</p>
        )}
      </li>
      <li>
        {todoCount === 0
          ? "No TODO or FIXME notes in the code."
          : `${plural(todoCount, "TODO or FIXME note")} in ${plural(debt.todo_file_count ?? 0, "file")}.`}
      </li>
      <li>{testFiles === 0 ? "No test files found." : `${plural(testFiles, "test file")}.`}</li>
    </ul>
  );
}

// The analysis results for the current repository (the old dashboard, minus its own header).
export function RepoOverview() {
  const repo = useRepo();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<DashboardAnalysis | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDashboard(repo.repo_id)
      .then((payload) => {
        if (!cancelled) {
          setAnalysis(payload.analysis);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load the analysis");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo.repo_id]);

  if (loading) {
    return <p className="notice">Loading the analysis...</p>;
  }
  if (error) {
    return (
      <p className="error" role="alert">
        Could not load the analysis: {error}
      </p>
    );
  }
  if (!analysis) {
    return <p className="notice">The analysis of this repository has not finished yet.</p>;
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Architecture summary</h2>
        <p className="muted">{analysis.architecture_summary || "Not available"}</p>
      </article>

      <article className="card">
        <h2>Code health</h2>
        <CodeHealth debt={analysis.tech_debt_flags} />
      </article>

      <article className="card">
        <h2>Contributors</h2>
        <pre className="mono">{pretty(analysis.contributor_stats)}</pre>
      </article>

      <article className="card">
        <h2>File tree</h2>
        <pre className="mono">{pretty(analysis.file_tree)}</pre>
      </article>
    </section>
  );
}
