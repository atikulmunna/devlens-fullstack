"use client";

import { useEffect, useState } from "react";
import { CodeHealth } from "@/components/overview/code-health";
import { Contributors } from "@/components/overview/contributors";
import { DependencyView } from "@/components/overview/dependency-view";
import { FileTree } from "@/components/overview/file-tree";
import { LanguageBar } from "@/components/overview/language-bar";
import { useRepo } from "@/components/repo-context";
import { DashboardAnalysis, getDashboard } from "@/lib/api";

// The analysis of the current repository: what it is, how it is built, and where to look first.
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

  const filePaths = Object.keys(analysis.file_tree?.files ?? {});
  return (
    <section className="overview">
      <article className="card">
        <h2>Architecture summary</h2>
        <p className="summary-text">{analysis.architecture_summary || "Not available"}</p>
      </article>

      <div className="overview-pair">
        <article className="card">
          <h2>Languages</h2>
          <LanguageBar languages={analysis.languages ?? []} />
        </article>
        <article className="card">
          <h2>Contributors</h2>
          <Contributors stats={analysis.contributor_stats} />
        </article>
      </div>

      <article className="card">
        <h2>Code health</h2>
        <CodeHealth debt={analysis.tech_debt_flags} githubUrl={repo.github_url} commitSha={analysis.commit_sha} />
      </article>

      <article className="card">
        <h2>Imports</h2>
        <DependencyView repoId={repo.repo_id} />
      </article>

      <article className="card">
        <h2>Files</h2>
        <FileTree paths={filePaths} githubUrl={repo.github_url} commitSha={analysis.commit_sha} />
      </article>
    </section>
  );
}
