import Link from "next/link";
import { getDashboard } from "@/lib/api";

type Props = {
  params: { repoId: string };
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export default async function DashboardPage({ params }: Props) {
  try {
    const payload = await getDashboard(params.repoId);
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
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return (
      <section className="grid">
        <article className="card">
          <h2>Repository Dashboard</h2>
          <p className="mono">Repo ID: {params.repoId}</p>
        </article>
        <article className="error">
          <strong>Failed to load dashboard:</strong> {message}
          <div>
            <Link href="/analyze">Back to analyze</Link>
          </div>
        </article>
      </section>
    );
  }
}
