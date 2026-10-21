import type { ContributorStats } from "@/lib/api";
import { plural } from "@/lib/format";
import { githubAvatarUrl, githubProfileUrl } from "@/lib/github-links";

export function Contributors({ stats }: { stats: ContributorStats | null }) {
  const people = stats?.top_contributors ?? [];
  if (stats?.error) {
    return <p className="muted">GitHub did not return contributors for this analysis.</p>;
  }
  if (people.length === 0) {
    return <p className="muted">No contributors were recorded.</p>;
  }
  return (
    <ul className="contributors">
      {people.map((person) => (
        <li key={person.username}>
          {/* Small GitHub avatars, as in the header; next/image optimization buys nothing here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={githubAvatarUrl(person.username)} alt="" width={32} height={32} loading="lazy" />
          <a href={githubProfileUrl(person.username)} rel="noreferrer">
            {person.username}
          </a>
          <span className="muted">{plural(person.commits, "commit")}</span>
        </li>
      ))}
    </ul>
  );
}
