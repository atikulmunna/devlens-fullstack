import type { ReactNode } from "react";
import { CodeHealth } from "@/components/overview/code-health";
import { Contributors } from "@/components/overview/contributors";
import { FileTree } from "@/components/overview/file-tree";
import { LanguageBar } from "@/components/overview/language-bar";
import type { DashboardAnalysis } from "@/lib/api";

type Props = {
  analysis: DashboardAnalysis;
  githubUrl: string;
  // The import explorer loads the dependency graph on its own; the shared page leaves it out.
  imports?: ReactNode;
};

// The analysis panels, shared by the Overview tab and the public share page.
export function OverviewSections({ analysis, githubUrl, imports }: Props) {
  const filePaths = Object.keys(analysis.file_tree?.files ?? {});
  return (
    <section className="overview">
      <article className="card">
        <h2>Architecture summary</h2>
        <p className="summary-text">{analysis.architecture_summary || "Not available"}</p>
      </article>

      <div className="overview-pair">
        <article className="card">
          <h2>Languages</h2>
          <LanguageBar languages={analysis.languages ?? []} />
        </article>
        <article className="card">
          <h2>Contributors</h2>
          <Contributors stats={analysis.contributor_stats} />
        </article>
      </div>

      <article className="card">
        <h2>Code health</h2>
        <CodeHealth debt={analysis.tech_debt_flags} githubUrl={githubUrl} commitSha={analysis.commit_sha} />
      </article>

      {imports && (
        <article className="card">
          <h2>Imports</h2>
          {imports}
        </article>
      )}

      <article className="card">
        <h2>Files</h2>
        <FileTree paths={filePaths} githubUrl={githubUrl} commitSha={analysis.commit_sha} />
      </article>
    </section>
  );
}
