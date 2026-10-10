"use client";

import { useEffect, useRef, useState } from "react";
import { getRepoStatusOnce, postAnalyze, RepoStatusSnapshot } from "@/lib/api";

export type AnalyzeJob = {
  jobId: string;
  repoId: string;
  cacheHit: boolean;
};

function isTerminal(stage: string): boolean {
  return stage === "done" || stage === "failed";
}

// Submits a repository for analysis and follows its progress over the status SSE stream,
// reconnecting (and reconciling with a one-shot status read) when the stream drops.
export function useAnalyzeJob() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<AnalyzeJob | null>(null);
  const [stage, setStage] = useState("queued");
  const [progress, setProgress] = useState(0);
  const streamRef = useRef<EventSource | null>(null);
  const reconnectRef = useRef(0);
  const stageRef = useRef(stage);

  useEffect(() => {
    stageRef.current = stage;
  }, [stage]);

  useEffect(() => {
    return () => {
      streamRef.current?.close();
      streamRef.current = null;
    };
  }, []);

  function closeStream(): void {
    if (streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
  }

  function applySnapshot(snapshot: RepoStatusSnapshot): void {
    const nextStage = snapshot.stage || "processing";
    setStage(nextStage);
    if (typeof snapshot.progress === "number") {
      setProgress(snapshot.progress);
    }
    if (nextStage === "failed") {
      setError(snapshot.message || "Analysis failed.");
    }
    if (isTerminal(nextStage)) {
      closeStream();
    }
  }

  async function reconcileStatus(repoId: string): Promise<void> {
    const snapshot = await getRepoStatusOnce(repoId);
    if (snapshot) {
      applySnapshot(snapshot);
    }
  }

  function connectStatus(repoId: string): void {
    closeStream();
    reconnectRef.current = 0;
    const stream = new EventSource(`/api/v1/repos/${encodeURIComponent(repoId)}/status`);
    streamRef.current = stream;

    stream.addEventListener("progress", (event) => {
      reconnectRef.current = 0;
      applySnapshot(JSON.parse(event.data) as RepoStatusSnapshot);
    });

    stream.addEventListener("done", (event) => {
      applySnapshot(JSON.parse(event.data) as RepoStatusSnapshot);
      setProgress(100);
    });

    stream.addEventListener("error", async () => {
      closeStream();
      if (isTerminal(stageRef.current)) {
        return;
      }
      reconnectRef.current += 1;
      try {
        await reconcileStatus(repoId);
      } catch {
        // The retry below covers a failed reconcile.
      }
      if (reconnectRef.current <= 5 && !isTerminal(stageRef.current)) {
        window.setTimeout(() => connectStatus(repoId), reconnectRef.current * 1000);
      } else if (!isTerminal(stageRef.current)) {
        setError("Lost the connection to the progress updates. Refresh the page to check again.");
      }
    });
  }

  async function start(githubUrl: string): Promise<void> {
    closeStream();
    setPending(true);
    setError(null);
    setJob(null);
    setStage("queued");
    setProgress(0);
    try {
      const payload = await postAnalyze({ github_url: githubUrl.trim() });
      setJob({ jobId: payload.job_id, repoId: payload.repo_id, cacheHit: payload.cache_hit });
      setStage(payload.status || "queued");
      connectStatus(payload.repo_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyze request failed");
    } finally {
      setPending(false);
    }
  }

  return { start, pending, error, job, stage, progress };
}
