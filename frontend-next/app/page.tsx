"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AnalyzeStatus } from "@/components/analyze-status";
import { ContourMap } from "@/components/contour-map";
import { getRecentRepos, RepoSummary } from "@/lib/api";
import { repoPath } from "@/lib/repo-path";
import { useAnalyzeJob } from "@/lib/use-analyze-job";

const EXAMPLES = ["pallets/itsdangerous", "psf/requests"];

export default function HomePage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [recent, setRecent] = useState<RepoSummary[]>([]);
  const { start, pending, error, job, stage, progress } = useAnalyzeJob();

  // The recent list is a convenience; the page works the same without it.
  useEffect(() => {
    getRecentRepos()
      .then(setRecent)
      .catch(() => setRecent([]));
  }, []);

  useEffect(() => {
    if (stage === "done" && job) {
      router.push(repoPath(job.fullName));
    }
  }, [stage, job, router]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void start(url);
  }

  return (
    <>
      <section className="hero">
        <div>
          <h1 className="hero-title">Understand a repository before you change it.</h1>
          <p className="hero-lede">
            Paste a public GitHub repository. DevLens reads its code, answers your questions with the files and lines
            it used, and shows how far a commit reaches.
          </p>
          <form className="repo-form" onSubmit={onSubmit}>
            <input
              className="input"
              aria-label="GitHub repository URL"
              placeholder="https://github.com/owner/repo"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            <button type="submit" className="button" disabled={pending}>
              {pending ? "Starting..." : "Analyze repository"}
            </button>
          </form>
          <p className="examples">
            Try{" "}
            {EXAMPLES.map((name, index) => (
              <span key={name}>
                {index > 0 && " or "}
                <button type="button" className="link-button" onClick={() => setUrl(`https://github.com/${name}`)}>
                  {name}
                </button>
              </span>
            ))}
            .
          </p>
          <AnalyzeStatus job={job} stage={stage} progress={progress} error={error} />
        </div>
        <ContourMap />
      </section>

      {recent.length > 0 && (
        <section className="recent" aria-labelledby="recent-heading">
          <h2 id="recent-heading">Recently analyzed</h2>
          <ul className="recent-list">
            {recent.map((repo) => (
              <li key={repo.repo_id}>
                <Link href={repoPath(repo.full_name)} className="mono">
                  {repo.full_name}
                </Link>
                {repo.description && <p>{repo.description}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <ul className="features">
        <li>
          <h2>Answers grounded in the code</h2>
          <p>Ask how something works and get an answer that names the files and lines it came from.</p>
        </li>
        <li>
          <h2>How far a change reaches</h2>
          <p>For the latest commit, see every file that imports what changed, and whether it touched sign-in, tokens, or secrets.</p>
        </li>
        <li>
          <h2>The shape of the project</h2>
          <p>Languages, contributors, and the file tree, gathered on one dashboard.</p>
        </li>
      </ul>
    </>
  );
}
