"use client";

import { createContext, useContext } from "react";
import { RepoSummary } from "@/lib/api";

// The repository a /r/{owner}/{repo} page is about, resolved once by the layout.
export const RepoContext = createContext<RepoSummary | null>(null);

export function useRepo(): RepoSummary {
  const repo = useContext(RepoContext);
  if (!repo) {
    throw new Error("useRepo must be used inside a repository page");
  }
  return repo;
}
