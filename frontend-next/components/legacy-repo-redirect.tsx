"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getDashboard } from "@/lib/api";
import { repoPath, RepoTab } from "@/lib/repo-path";

// Old id-based links (/dashboard/{id}, /diff/{id}, /workspace?repo={id}) forward to the
// readable /r/{owner}/{repo} address so existing bookmarks keep working.
export function LegacyRepoRedirect({ repoId, tab }: { repoId: string; tab: RepoTab }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard(repoId)
      .then((payload) => router.replace(repoPath(payload.repository.full_name, tab)))
      .catch((err) => setError(err instanceof Error ? err.message : "Repository not found"));
  }, [repoId, tab, router]);

  if (error) {
    return (
      <p className="error" role="alert">
        This link points to a repository DevLens no longer has: {error}
      </p>
    );
  }
  return <p className="notice">Opening the repository...</p>;
}
