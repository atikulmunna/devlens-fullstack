export type LineRange = { start: number; end?: number };

// A file (and optionally its lines) on GitHub at the commit DevLens analyzed, so a link shows
// exactly the code the analysis read. Without a known commit it falls back to the default branch.
export function githubFileUrl(
  githubUrl: string,
  commitSha: string | null | undefined,
  path: string,
  lines?: LineRange
): string {
  const ref = commitSha || "HEAD";
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  let anchor = "";
  if (lines) {
    anchor = lines.end && lines.end > lines.start ? `#L${lines.start}-L${lines.end}` : `#L${lines.start}`;
  }
  return `${githubUrl.replace(/\/+$/, "")}/blob/${ref}/${encodedPath}${anchor}`;
}

export function githubProfileUrl(username: string): string {
  return `https://github.com/${encodeURIComponent(username)}`;
}

export function githubAvatarUrl(username: string, size = 64): string {
  return `https://github.com/${encodeURIComponent(username)}.png?size=${size}`;
}
