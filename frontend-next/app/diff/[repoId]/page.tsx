"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { askAboutDiffStream, CommitDiffSummary, getCommitDiff } from "@/lib/api";

type Props = {
  params: { repoId: string };
};

export default function DiffPage({ params }: Props) {
  const repoId = params.repoId;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diff, setDiff] = useState<CommitDiffSummary | null>(null);

  const [question, setQuestion] = useState("Does this commit touch auth or secrets, and what is the blast radius?");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const summary = await getCommitDiff(repoId);
        if (!cancelled) {
          setDiff(summary);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load commit diff");
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
  }, [repoId]);

  async function onAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = question.trim();
    if (!q || asking) {
      return;
    }
    setAsking(true);
    setAnswer("");
    setError(null);
    try {
      await askAboutDiffStream(repoId, q, {
        onToken: (token) => setAnswer((prev) => prev + token),
        onDone: () => undefined
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Diff question failed");
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Commit Diff Intelligence</h2>
        <p className="mono">Repo ID: {repoId}</p>
        <div className="row">
          <Link href={`/dashboard/${encodeURIComponent(repoId)}`}>Dashboard</Link>
          <Link href={`/workspace?repo=${encodeURIComponent(repoId)}`}>Workspace / set token</Link>
        </div>
      </article>

      {loading && <article className="notice">Loading latest commit diff...</article>}

      {error && (
        <article className="error">
          <strong>Problem:</strong> {error}
          <div className="muted" style={{ marginTop: 6 }}>
            If this says unauthorized, set an access token in the Workspace first.
          </div>
        </article>
      )}

      {diff && (
        <>
          <article className="card">
            <h3>Commit</h3>
            <p className="mono">
              {diff.base_sha ? `${diff.base_sha.slice(0, 10)} -> ` : ""}
              {diff.head_sha.slice(0, 10)}
            </p>
            <p className="muted">
              {diff.changed_files.length} changed file(s), blast radius: {diff.blast_radius.impacted_count} impacted
              file(s).
            </p>
          </article>

          {diff.security_flags.length > 0 && (
            <article className="error">
              <strong>Security-sensitive changes:</strong>
              <div className="citations">
                {diff.security_flags.map((flag) => (
                  <span key={flag.path} className="citation-pill mono">
                    {flag.path} [{flag.categories.join(", ")}]
                  </span>
                ))}
              </div>
            </article>
          )}

          <article className="card">
            <h3>Changed files</h3>
            <div className="grid">
              {diff.changed_files.map((file) => (
                <div key={file.path} className="row" style={{ justifyContent: "space-between" }}>
                  <span className="mono">{file.path}</span>
                  <span className="muted">
                    {file.status} · +{file.added} / -{file.removed} · {file.hunks} hunk(s)
                  </span>
                </div>
              ))}
            </div>
          </article>

          {diff.blast_radius.impacted_files.length > 0 && (
            <article className="card">
              <h3>Blast radius (impacted importers)</h3>
              <div className="citations">
                {diff.blast_radius.impacted_files.map((path) => (
                  <span key={path} className="citation-pill mono">
                    {path}
                  </span>
                ))}
              </div>
            </article>
          )}

          <article className="card">
            <h3>Ask about this diff</h3>
            <form className="grid" onSubmit={onAsk}>
              <input
                className="input"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What changed and why is it risky?"
              />
              <div className="row">
                <button type="submit" className="button" disabled={asking || !question.trim()}>
                  {asking ? "Thinking..." : "Ask"}
                </button>
              </div>
            </form>
            {(answer || asking) && (
              <div className="bubble assistant" style={{ marginTop: 12, maxWidth: "100%" }}>
                <div className="role">answer</div>
                <div className={asking && !answer ? "blink" : undefined}>{answer}</div>
              </div>
            )}
          </article>
        </>
      )}
    </section>
  );
}
