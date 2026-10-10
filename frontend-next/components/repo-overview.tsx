"use client";

import { useEffect, useState } from "react";
import { useRepo } from "@/components/repo-context";
import { DashboardAnalysis, getDashboard } from "@/lib/api";

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
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
        <h2>Quality score</h2>
        <p>{analysis.quality_score ?? "Not available"}</p>
      </article>

      <article className="card">
        <h2>Architecture summary</h2>
        <p className="muted">{analysis.architecture_summary || "Not available"}</p>
      </article>

      <article className="card">
        <h2>Tech debt flags</h2>
        <pre className="mono">{pretty(analysis.tech_debt_flags)}</pre>
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
