"use client";

import { useEffect, useState } from "react";
import { LoadingCards } from "@/components/loading";
import { OverviewSections } from "@/components/overview/overview-sections";
import { getSharedAnalysis, SharedAnalysis } from "@/lib/api";
import { sharedLinkError } from "@/lib/errors";
import { longDate } from "@/lib/format";

// A repository overview someone shared: read-only, no sign-in, everything from the one share response.
export default function SharedOverviewPage({ params }: { params: { token: string } }) {
  const [shared, setShared] = useState<SharedAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSharedAnalysis(params.token)
      .then((payload) => {
        if (!cancelled) {
          setShared(payload);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(sharedLinkError(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.token]);

  if (error) {
    return (
      <section className="repo-missing">
        <h1 className="repo-title">This shared link does not open</h1>
        <p className="muted">{error}</p>
      </section>
    );
  }
  if (!shared) {
    return <LoadingCards label="Opening the shared overview" cards={[3, 2, 4]} />;
  }

  const { repository, analysis } = shared;
  return (
    <>
      <header className="repo-header">
        <h1 className="repo-title">{repository.full_name}</h1>
        {repository.description && <p className="repo-description">{repository.description}</p>}
        <div className="repo-meta">
          <a href={repository.github_url} target="_blank" rel="noreferrer">
            View on GitHub
          </a>
          {repository.language && <span>{repository.language}</span>}
          <span>Shared overview, open until {longDate(shared.expires_at)}</span>
        </div>
      </header>
      <OverviewSections analysis={analysis} githubUrl={repository.github_url} />
    </>
  );
}
