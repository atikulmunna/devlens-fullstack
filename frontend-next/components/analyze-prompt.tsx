"use client";

import { useEffect } from "react";
import { AnalyzeStatus } from "@/components/analyze-status";
import { useAnalyzeJob } from "@/lib/use-analyze-job";

type Props = {
  fullName: string;
  // Called once the analysis finishes; pass a stable function (useCallback).
  onDone: () => void;
};

// A button that analyzes the repository, with the analysis steps below it while it runs.
export function AnalyzePrompt({ fullName, onDone }: Props) {
  const analysis = useAnalyzeJob();

  useEffect(() => {
    if (analysis.stage === "done" && analysis.job) {
      onDone();
    }
  }, [analysis.stage, analysis.job, onDone]);

  return (
    <>
      <button
        type="button"
        className="button"
        disabled={analysis.pending || Boolean(analysis.job)}
        onClick={() => void analysis.start(`https://github.com/${fullName}`)}
      >
        Analyze {fullName}
      </button>
      <AnalyzeStatus
        job={analysis.job}
        stage={analysis.stage}
        failedStage={analysis.failedStage}
        counts={analysis.counts}
        error={analysis.error}
      />
    </>
  );
}
