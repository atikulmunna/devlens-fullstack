"use client";

import { FormEvent, useEffect, useState } from "react";
import { SignInLink, useAuth } from "@/components/auth";
import { BlastMap } from "@/components/changes/blast-map";
import { FileDiff } from "@/components/changes/file-diff";
import { SEVERITY_ORDER, SeverityBadge } from "@/components/changes/severity";
import { Answer } from "@/components/chat/answer";
import { LoadingCards } from "@/components/loading";
import { useRepo } from "@/components/repo-context";
import {
  askAboutDiffStream,
  CommitDiffEntry,
  CommitDiffSummary,
  getCommitDiff,
  listCommitDiffs
} from "@/lib/api";
import { ApiError, friendlyChatError } from "@/lib/errors";
import { plural } from "@/lib/format";

function shortDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
}

// An analyzed commit's changes: which files, which lines, how risky, and how far they reach.
export function RepoChanges() {
  const repo = useRepo();
  const { status } = useAuth();
  const [commits, setCommits] = useState<CommitDiffEntry[]>([]);
  const [head, setHead] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diff, setDiff] = useState<CommitDiffSummary | null>(null);
  // No commit changes stored for this repository: an empty state, not an error.
  const [none, setNone] = useState(false);
  const [question, setQuestion] = useState("Does this commit touch sign-in or secrets, and what does it affect?");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    if (status !== "signed-in") {
      return;
    }
    listCommitDiffs(repo.repo_id)
      .then(setCommits)
      .catch(() => setCommits([]));
  }, [repo.repo_id, status]);

  useEffect(() => {
    if (status !== "signed-in") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNone(false);
    setAnswer("");
    getCommitDiff(repo.repo_id, head ?? undefined)
      .then((summary) => {
        if (!cancelled) {
          setDiff(summary);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDiff(null);
          if (err instanceof ApiError && err.status === 404) {
            setNone(true);
          } else {
            setError(friendlyChatError(err));
          }
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
  }, [repo.repo_id, status, head]);

  async function onAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = question.trim();
    if (!q || asking || !diff) {
      return;
    }
    setAsking(true);
    setAnswer("");
    setError(null);
    try {
      await askAboutDiffStream(
        repo.repo_id,
        q,
        { onToken: (token) => setAnswer((prev) => prev + token), onDone: () => undefined },
        diff.head_sha
      );
    } catch (err) {
      setError(friendlyChatError(err));
    } finally {
      setAsking(false);
    }
  }

  if (status === "loading") {
    return <LoadingCards label="Checking sign-in" cards={[1, 4]} />;
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

  const flags = [...(diff?.security_flags ?? [])].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || a.path.localeCompare(b.path)
  );
  const flagByPath = new Map(flags.map((flag) => [flag.path, flag]));
  const byDepth = diff?.blast_radius.impacted_by_depth ?? [];
  const compareUrl = diff?.base_sha ? `${repo.github_url}/compare/${diff.base_sha}...${diff.head_sha}` : null;

  return (
    <section className="changes">
      <div className="commit-bar">
        {commits.length > 1 && (
          <label className="commit-picker">
            <span>Commit</span>
            <select className="input" value={diff?.head_sha ?? ""} onChange={(event) => setHead(event.target.value)}>
              {commits.map((commit) => (
                <option key={commit.head_sha} value={commit.head_sha}>
                  {commit.head_sha.slice(0, 7)}, {plural(commit.changed_count, "file")}, analyzed {shortDate(commit.created_at)}
                </option>
              ))}
            </select>
          </label>
        )}
        {diff && (
          <p className="commit-line">
            <a className="mono" href={`${repo.github_url}/commit/${diff.head_sha}`} target="_blank" rel="noreferrer">
              {diff.head_sha.slice(0, 10)}
            </a>
            {compareUrl && (
              <>
                {" "}
                <span className="muted">against its parent</span>{" "}
                <a href={compareUrl} target="_blank" rel="noreferrer">
                  compare on GitHub
                </a>
              </>
            )}
          </p>
        )}
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading && <LoadingCards label="Loading the commit" cards={[1, 6, 4]} />}

      {none && !loading && (
        <article className="card empty-state">
          <h2>No commit changes yet</h2>
          <p className="muted">
            DevLens records a commit&apos;s changes when it analyzes the commit, by comparing it with the one before.
            Nothing is stored for {repo.full_name} yet: it may have a single commit, or it was analyzed before changes
            were recorded. Changes show up here after DevLens analyzes a newer commit.
          </p>
        </article>
      )}

      {diff && !loading && (
        <>
          <p className="changes-summary">
            {plural(diff.changed_files.length, "file")} changed. {plural(diff.blast_radius.impacted_count, "other file")}{" "}
            import them{byDepth.length > 1 ? `, up to ${plural(byDepth.length, "import")} away` : ""}.
            {flags.length > 0 && ` ${plural(flags.length, "file")} touch security-sensitive code.`}
          </p>

          {flags.length > 0 && (
            <article className="card">
              <h2>Security-sensitive changes</h2>
              <ul className="flags">
                {flags.map((flag) => (
                  <li key={flag.path}>
                    <SeverityBadge level={flag.severity} />
                    <span className="mono">{flag.path}</span>
                    <span className="muted">{flag.categories.join(", ")}</span>
                  </li>
                ))}
              </ul>
            </article>
          )}

          <article className="card">
            <h2>Changed files</h2>
            <div className="file-diffs">
              {diff.changed_files.map((file) => (
                <FileDiff key={file.path} file={file} flag={flagByPath.get(file.path)} />
              ))}
            </div>
          </article>

          <article className="card">
            <h2>How far it reaches</h2>
            {diff.blast_radius.impacted_count === 0 ? (
              <p className="muted">No other indexed file imports the changed files.</p>
            ) : (
              <>
                <BlastMap changed={diff.blast_radius.changed_files} byDepth={byDepth} />
                <ol className="reach-list">
                  {byDepth.map((level, index) => (
                    <li key={index}>
                      <span className="muted">
                        {index === 0 ? "Import a changed file" : `${index + 1} imports away`} ({level.length})
                      </span>
                      <span className="mono">{level.join(", ")}</span>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </article>

          <article className="card">
            <h2>Ask about this commit</h2>
            <form className="chat-form" onSubmit={onAsk}>
              <input
                className="input"
                aria-label="Question about this commit"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <button type="submit" className="button" disabled={asking || !question.trim()}>
                {asking ? "Answering..." : "Ask"}
              </button>
            </form>
            {answer && (
              <div className={`diff-answer${asking ? " blink" : ""}`}>
                <Answer content={answer} citations={[]} githubUrl={repo.github_url} />
              </div>
            )}
          </article>
        </>
      )}
    </section>
  );
}
