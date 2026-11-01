"use client";

import { useEffect, useState } from "react";
import { LoadingBlock } from "@/components/loading";
import { getHotspots, Hotspots } from "@/lib/api";
import { windowLabel } from "@/lib/format";
import { githubFileUrl } from "@/lib/github-links";

type Props = { repoId: string; githubUrl: string; commitSha: string | null | undefined };

// Files that change often and that many others import: a change there is likely, and it reaches far.
// Loads its own data, like the import explorer, so the shared overview page leaves it out.
export function HotspotsView({ repoId, githubUrl, commitSha }: Props) {
  const [data, setData] = useState<Hotspots | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHotspots(repoId)
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load hotspots");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repoId]);

  if (error) {
    return <p className="error">Could not load hotspots: {error}</p>;
  }
  if (!data) {
    return <LoadingBlock label="Loading hotspots" />;
  }
  if (!data.measured) {
    return (
      <p className="muted">This analysis has no change history. Analyze the repository again to see its hotspots.</p>
    );
  }
  const window = windowLabel(data.window_days);
  if (data.hotspots.length === 0) {
    return <p className="muted">No code file changed more than once in {window}.</p>;
  }
  return (
    <div className="hotspots">
      <p className="muted">
        Ranked by changes in {window} times the files that import each one. Hard-to-change code costs the most here.
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col" className="numeric">
              Changes
            </th>
            <th scope="col" className="numeric">
              Imported by
            </th>
          </tr>
        </thead>
        <tbody>
          {data.hotspots.map((hotspot) => (
            <tr key={hotspot.path}>
              <td className="mono">
                <a href={githubFileUrl(githubUrl, commitSha, hotspot.path)} rel="noreferrer">
                  {hotspot.path}
                </a>
              </td>
              <td className="numeric">{hotspot.changes}</td>
              <td className="numeric">{hotspot.importers}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
