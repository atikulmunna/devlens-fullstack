"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LegacyRepoRedirect } from "@/components/legacy-repo-redirect";

// The old workspace merged into the repository pages: /workspace?repo={id} opens that
// repository's chat; a bare /workspace goes home.
export default function LegacyWorkspacePage() {
  const router = useRouter();
  const [repoId, setRepoId] = useState<string | null>(null);

  useEffect(() => {
    const repo = new URLSearchParams(window.location.search).get("repo");
    if (repo) {
      setRepoId(repo);
    } else {
      router.replace("/");
    }
  }, [router]);

  return repoId ? <LegacyRepoRedirect repoId={repoId} tab="chat" /> : <p className="notice">Opening...</p>;
}
