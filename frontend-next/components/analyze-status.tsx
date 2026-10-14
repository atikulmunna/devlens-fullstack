import Link from "next/link";
import { AnalyzeCounts, analyzeSteps, StepState } from "@/lib/analyze-steps";
import { repoPath } from "@/lib/repo-path";
import { AnalyzeJob } from "@/lib/use-analyze-job";

const STATE_TEXT: Record<StepState, string> = {
  done: "done",
  current: "in progress",
  waiting: "not started",
  failed: "failed"
};

type Props = {
  job: AnalyzeJob | null;
  stage: string;
  failedStage: string | null;
  counts: AnalyzeCounts | null;
  error: string | null;
};

// The analysis drawn as a route: one waypoint per worker step, with counts as they become known.
// Pages that show this move on to the repository by themselves once it is done; the link is
// the fallback if that navigation is slow or blocked.
export function AnalyzeStatus({ job, stage, failedStage, counts, error }: Props) {
  const errorBox = error && (
    <div className="error" role="alert">
      Analysis did not finish: {error}
    </div>
  );
  if (!job) {
    return errorBox ? <div className="analyze-progress">{errorBox}</div> : null;
  }

  const steps = analyzeSteps(stage, failedStage, counts);
  const current = steps.find((step) => step.state === "current");
  return (
    <div className="analyze-progress">
      <ol className="steps">
        {steps.map((step) => (
          <li
            key={step.label}
            className={`step step-${step.state}`}
            aria-current={step.state === "current" ? "step" : undefined}
          >
            <span className="step-label">{step.label}</span>
            <span className="visually-hidden">, {STATE_TEXT[step.state]}</span>
            {step.detail && <span className="step-detail">{step.detail}</span>}
          </li>
        ))}
      </ol>
      {stage === "done" && (
        <p className="step-note" role="status">
          {job.cacheHit ? "Already analyzed." : "Analysis finished."} Opening{" "}
          <Link href={repoPath(job.fullName)}>{job.fullName}</Link>...
        </p>
      )}
      {stage === "queued" && (
        <p className="step-note" role="status">
          Waiting to start.
        </p>
      )}
      {current && (
        <p className="visually-hidden" role="status">
          {current.label}
        </p>
      )}
      {errorBox}
    </div>
  );
}
