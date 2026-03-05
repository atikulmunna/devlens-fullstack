"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DashboardResponse, getDashboard } from "@/lib/api";

type Props = {
  params: { repoId: string };
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export default function DashboardPage({ params }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<DashboardResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const response = await getDashboard(params.repoId);
        if (!cancelled) {
          setPayload(response);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown dashboard error";
        if (!cancelled) {
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [params.repoId]);

  if (loading) {
    return (
      <section className="grid">
        <article className="card">
          <h2>Repository Dashboard</h2>
          <p className="mono">Repo ID: {params.repoId}</p>
        </article>
        <article className="notice">Loading dashboard data...</article>
      </section>
    );
  }

  if (error || !payload) {
    return (
      <section className="grid">
        <article className="card">
          <h2>Repository Dashboard</h2>
          <p className="mono">Repo ID: {params.repoId}</p>
        </article>
        <article className="error">
          <strong>Failed to load dashboard:</strong> {error || "Unknown error"}
          <div>
            <Link href="/analyze">Back to analyze</Link>
          </div>
        </article>
      </section>
    );
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Repository Dashboard</h2>
        <p className="muted">{payload.full_name}</p>
        <p className="mono">Repo ID: {payload.repo_id}</p>
        <p>
          <a href={payload.github_url} target="_blank" rel="noreferrer">
            {payload.github_url}
          </a>
        </p>
      </article>

      <article className="card">
        <h2>Quality Score</h2>
        <p>{payload.quality_score}</p>
      </article>

      <article className="card">
        <h2>Architecture Summary</h2>
        <p className="muted">{payload.architecture_summary}</p>
      </article>

      <article className="card">
        <h2>Tech Debt Flags</h2>
        <pre className="mono">{pretty(payload.tech_debt_flags)}</pre>
      </article>

      <article className="card">
        <h2>Contributors</h2>
        <pre className="mono">{pretty(payload.contributor_stats)}</pre>
      </article>

      <article className="card">
        <h2>File Tree</h2>
        <pre className="mono">{pretty(payload.file_tree)}</pre>
      </article>
    </section>
  );
}
