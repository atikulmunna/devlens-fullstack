import Link from "next/link";
import { repoPath } from "@/lib/repo-path";
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

// Pages that show this move on to the repository by themselves once it is done; the link is
// the fallback if that navigation is slow or blocked.
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
  if (stage === "done") {
    return (
      <div className="notice analyze-progress" role="status">
        {job.cacheHit ? "Already analyzed." : "Analysis finished."} Opening{" "}
        <Link href={repoPath(job.fullName)}>{job.fullName}</Link>...
      </div>
    );
  }
  return (
    <div className="notice analyze-progress" role="status">
      {STAGE_TEXT[stage] || "Working"} ({progress}%)
    </div>
  );
}
