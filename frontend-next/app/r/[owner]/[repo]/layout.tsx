"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { AnalyzeStatus } from "@/components/analyze-status";
import { RepoContext } from "@/components/repo-context";
import { getRepoByName, RepoSummary } from "@/lib/api";
import { repoPath, RepoTab, tabFromPath } from "@/lib/repo-path";
import { useAnalyzeJob } from "@/lib/use-analyze-job";

type Props = {
  children: ReactNode;
  params: { owner: string; repo: string };
};

const TABS: { tab: RepoTab; label: string }[] = [
  { tab: "overview", label: "Overview" },
  { tab: "chat", label: "Chat" },
  { tab: "changes", label: "Changes" }
];

export default function RepoLayout({ children, params }: Props) {
  const requestedName = `${decodeURIComponent(params.owner)}/${decodeURIComponent(params.repo)}`;
  const pathname = usePathname() || "";
  const router = useRouter();
  const analysis = useAnalyzeJob();
  const [repo, setRepo] = useState<RepoSummary | null>(null);
  const [state, setState] = useState<"loading" | "found" | "missing" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const [owner, name] = requestedName.split("/");
    getRepoByName(owner, name)
      .then((found) => {
        if (!cancelled) {
          setRepo(found);
          setState(found ? "found" : "missing");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load the repository");
          setState("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [requestedName, reloadKey]);

  // GitHub names are case-insensitive; keep shared links on the canonical spelling.
  useEffect(() => {
    if (repo && repo.full_name !== requestedName) {
      router.replace(repoPath(repo.full_name, tabFromPath(pathname)));
    }
  }, [repo, requestedName, pathname, router]);

  // An analysis started from the "not analyzed yet" view loads the page when it finishes.
  useEffect(() => {
    if (analysis.stage === "done" && analysis.job) {
      setReloadKey((key) => key + 1);
    }
  }, [analysis.stage, analysis.job]);

  if (state === "loading") {
    return <p className="notice">Loading {requestedName}...</p>;
  }
  if (state === "error") {
    return (
      <p className="error" role="alert">
        Could not load {requestedName}: {error}
      </p>
    );
  }
  if (state === "missing" || !repo) {
    return (
      <section className="repo-missing">
        <h1 className="repo-title">{requestedName}</h1>
        <p className="muted">DevLens has not analyzed this repository yet.</p>
        <button
          type="button"
          className="button"
          disabled={analysis.pending || Boolean(analysis.job)}
          onClick={() => void analysis.start(`https://github.com/${requestedName}`)}
        >
          Analyze {requestedName}
        </button>
        <AnalyzeStatus job={analysis.job} stage={analysis.stage} progress={analysis.progress} error={analysis.error} />
      </section>
    );
  }

  const activeTab = tabFromPath(pathname);
  return (
    <RepoContext.Provider value={repo}>
      <header className="repo-header">
        <h1 className="repo-title">{repo.full_name}</h1>
        {repo.description && <p className="repo-description">{repo.description}</p>}
        <p className="repo-meta">
          <a href={repo.github_url} target="_blank" rel="noreferrer">
            View on GitHub
          </a>
          {repo.language && <span>{repo.language}</span>}
        </p>
        <nav className="tabs" aria-label="Repository">
          {TABS.map(({ tab, label }) => (
            <Link
              key={tab}
              href={repoPath(repo.full_name, tab)}
              className="tab"
              aria-current={activeTab === tab ? "page" : undefined}
            >
              {label}
            </Link>
          ))}
        </nav>
      </header>
      {children}
    </RepoContext.Provider>
  );
}
