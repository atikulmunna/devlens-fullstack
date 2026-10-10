export type RepoTab = "overview" | "chat" | "changes";

// Readable address for a repository page, e.g. /r/pallets/itsdangerous/chat.
export function repoPath(fullName: string, tab: RepoTab = "overview"): string {
  const [owner, name] = fullName.split("/");
  const base = `/r/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;
  return tab === "overview" ? base : `${base}/${tab}`;
}

// Which repository tab a /r/{owner}/{repo}[/{tab}] path shows. Position matters, not the last
// segment: a repository may itself be named "chat" or "changes".
export function tabFromPath(pathname: string): RepoTab {
  const tab = pathname.split("/").filter(Boolean)[3];
  return tab === "chat" || tab === "changes" ? tab : "overview";
}
