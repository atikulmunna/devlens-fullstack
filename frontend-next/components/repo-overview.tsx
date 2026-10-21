"use client";

import { useCallback, useEffect, useState } from "react";
import { AnalyzePrompt } from "@/components/analyze-prompt";
import { LoadingCards } from "@/components/loading";
import { DependencyView } from "@/components/overview/dependency-view";
import { OverviewSections } from "@/components/overview/overview-sections";
import { useRepo } from "@/components/repo-context";
import { DashboardAnalysis, getDashboard } from "@/lib/api";

// The analysis of the current repository: what it is, how it is built, and where to look first.
export function RepoOverview() {
  const repo = useRepo();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<DashboardAnalysis | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

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
  }, [repo.repo_id, reloadKey]);

  if (loading) {
    return <LoadingCards label="Loading the analysis" cards={[3, 2, 4]} />;
  }
  if (error) {
    return (
      <p className="error" role="alert">
        Could not load the analysis: {error}
      </p>
    );
  }
  if (!analysis) {
    return (
      <article className="card empty-state">
        <h2>No finished analysis yet</h2>
        <p className="muted">
          An analysis of {repo.full_name} is still running, or the last one stopped before it finished. Analyze it to
          follow the progress here; this page fills in when it is done.
        </p>
        <AnalyzePrompt fullName={repo.full_name} onDone={reload} />
      </article>
    );
  }

  return (
    <OverviewSections
      analysis={analysis}
      githubUrl={repo.github_url}
      imports={<DependencyView repoId={repo.repo_id} />}
    />
  );
}
