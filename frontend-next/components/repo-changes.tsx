"use client";

import { FormEvent, useEffect, useState } from "react";
import { SignInLink, useAuth } from "@/components/auth";
import { useRepo } from "@/components/repo-context";
import { askAboutDiffStream, CommitDiffSummary, getCommitDiff } from "@/lib/api";
import { plural } from "@/lib/format";

// The latest commit's changes, what they affect, and a question box about them.
export function RepoChanges() {
  const repo = useRepo();
  const { status } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diff, setDiff] = useState<CommitDiffSummary | null>(null);
  const [question, setQuestion] = useState("Does this commit touch sign-in or secrets, and what does it affect?");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    if (status !== "signed-in") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCommitDiff(repo.repo_id)
      .then((summary) => {
        if (!cancelled) {
          setDiff(summary);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load the commit changes");
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
  }, [repo.repo_id, status]);

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
      await askAboutDiffStream(repo.repo_id, q, {
        onToken: (token) => setAnswer((prev) => prev + token),
        onDone: () => undefined
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The question could not be answered");
    } finally {
      setAsking(false);
    }
  }

  if (status === "loading") {
    return <p className="notice">Checking sign-in...</p>;
  }
  if (status === "signed-out") {
    return (
      <article className="card">
        <h2>Sign in to see what changed in {repo.full_name}</h2>
        <p className="muted">Commit changes use your GitHub sign-in.</p>
        <SignInLink>Sign in with GitHub</SignInLink>
      </article>
    );
  }
  if (loading) {
    return <p className="notice">Loading the latest commit...</p>;
  }

  return (
    <section className="grid">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {diff && (
        <>
          <article className="card">
            <h2>Latest commit</h2>
            <p className="mono">
              {diff.base_sha ? `${diff.base_sha.slice(0, 10)} to ` : ""}
              {diff.head_sha.slice(0, 10)}
            </p>
            <p className="muted">
              {plural(diff.changed_files.length, "file")} changed, {plural(diff.blast_radius.impacted_count, "other file")}{" "}
              import them.
            </p>
          </article>

          {diff.security_flags.length > 0 && (
            <article className="error">
              <strong>Touches sign-in, tokens, or secrets</strong>
              <div className="citations">
                {diff.security_flags.map((flag) => (
                  <span key={flag.path} className="citation-pill mono">
                    {flag.path} ({flag.categories.join(", ")})
                  </span>
                ))}
              </div>
            </article>
          )}

          <article className="card">
            <h2>Changed files</h2>
            <div className="grid">
              {diff.changed_files.map((file) => (
                <div key={file.path} className="changed-file">
                  <span className="mono">{file.path}</span>
                  <span className="muted">
                    {file.status}, +{file.added} / -{file.removed}, {plural(file.hunks, "hunk")}
                  </span>
                </div>
              ))}
            </div>
          </article>

          {diff.blast_radius.impacted_files.length > 0 && (
            <article className="card">
              <h2>Files that import the changes</h2>
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
            <h2>Ask about this commit</h2>
            <form className="chat-form" onSubmit={onAsk}>
              <input
                className="input"
                aria-label="Question about this commit"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button type="submit" className="button" disabled={asking || !question.trim()}>
                {asking ? "Answering..." : "Ask"}
              </button>
            </form>
            {(answer || asking) && (
              <div className="bubble assistant diff-answer">
                <div className="role">DevLens</div>
                <div className={asking && !answer ? "blink" : undefined}>{answer}</div>
              </div>
            )}
          </article>
        </>
      )}
    </section>
  );
}
