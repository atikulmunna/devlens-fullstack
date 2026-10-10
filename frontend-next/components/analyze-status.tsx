import Link from "next/link";
import { AnalyzeJob } from "@/lib/use-analyze-job";

const STAGE_TEXT: Record<string, string> = {
  queued: "Waiting to start",
  cloning: "Fetching the code",
  parsing: "Reading the files",
  embedding: "Indexing for search",
  analyzing: "Summarizing the repository",
  done: "Ready"
};

type Props = {
  job: AnalyzeJob | null;
  stage: string;
  progress: number;
  error: string | null;
};

export function AnalyzeStatus({ job, stage, progress, error }: Props) {
  if (error) {
    return (
      <div className="error analyze-progress" role="alert">
        Analysis did not finish: {error}
      </div>
    );
  }
  if (!job) {
    return null;
  }

  const repo = encodeURIComponent(job.repoId);
  if (stage === "done") {
    return (
      <div className="notice analyze-progress" role="status">
        {job.cacheHit ? "Already analyzed at this commit." : "Analysis finished."}{" "}
        <Link href={`/dashboard/${repo}`}>Open the dashboard</Link> or{" "}
        <Link href={`/workspace?repo=${repo}`}>ask about the code</Link>.
      </div>
    );
  }
  return (
    <div className="notice analyze-progress" role="status">
      {STAGE_TEXT[stage] || "Working"} ({progress}%)
    </div>
  );
}
