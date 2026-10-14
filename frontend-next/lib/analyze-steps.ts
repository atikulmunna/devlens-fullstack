import { plural } from "./format";

export type StepState = "done" | "current" | "waiting" | "failed";

export type AnalyzeCounts = {
  files: number;
  chunks: number;
  indexedChunks: number;
};

export type AnalyzeStep = {
  label: string;
  state: StepState;
  detail: string | null;
};

// The job stages the workers report, in the order they run.
const STEPS = [
  { stage: "cloning", label: "Fetch the code" },
  { stage: "parsing", label: "Read the files" },
  { stage: "embedding", label: "Index for search" },
  { stage: "analyzing", label: "Summarize the repository" }
];

function stepIndex(stage: string | null): number {
  if (stage === "done") {
    return STEPS.length;
  }
  return STEPS.findIndex((step) => step.stage === stage);
}

function stepDetail(stage: string, state: StepState, counts: AnalyzeCounts | null): string | null {
  if (!counts || counts.chunks === 0) {
    return null;
  }
  if (stage === "parsing" && state === "done") {
    return `${plural(counts.files, "file")}, ${plural(counts.chunks, "code section")}`;
  }
  if (stage === "embedding" && state === "current") {
    return `${counts.indexedChunks.toLocaleString("en-US")} of ${plural(counts.chunks, "section")}`;
  }
  if (stage === "embedding" && state === "done") {
    return `${plural(counts.chunks, "section")} searchable`;
  }
  return null;
}

// `failedStage` is the stage that was running when the job failed; a failure before any step
// started (or one we never saw start) is shown on the first step.
export function analyzeSteps(stage: string, failedStage: string | null, counts: AnalyzeCounts | null): AnalyzeStep[] {
  const failed = stage === "failed";
  const reached = failed ? Math.max(stepIndex(failedStage), 0) : stepIndex(stage);
  return STEPS.map((step, index) => {
    let state: StepState = "waiting";
    if (index < reached) {
      state = "done";
    } else if (index === reached) {
      state = failed ? "failed" : "current";
    }
    return { label: step.label, state, detail: stepDetail(step.stage, state, counts) };
  });
}
