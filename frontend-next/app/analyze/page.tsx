"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { getRepoStatusOnce, postAnalyze, RepoStatusSnapshot } from "@/lib/api";

type AnalyzeResult = {
  job_id: string;
  repo_id: string;
  status: string;
  cache_hit: boolean;
};

function isTerminal(stage: string): boolean {
  return stage === "done" || stage === "failed";
}

export default function AnalyzePage() {
  const [url, setUrl] = useState("https://github.com/psf/requests");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [stage, setStage] = useState<string>("queued");
  const [progress, setProgress] = useState<number>(0);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);
  const [cacheHit, setCacheHit] = useState(false);
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

  async function reconcileStatus(repoId: string): Promise<void> {
    const snapshot = await getRepoStatusOnce(repoId);
    if (!snapshot) {
      return;
    }
    applySnapshot(snapshot, repoId);
  }

  function applySnapshot(snapshot: RepoStatusSnapshot, repoId: string): void {
    const nextStage = snapshot.stage || "processing";
    setStage(nextStage);
    if (typeof snapshot.progress === "number") {
      setProgress(snapshot.progress);
    }
    if (nextStage === "done") {
      setDoneMessage(`Analysis complete for ${repoId}.`);
      closeStream();
      return;
    }
    if (nextStage === "failed") {
      setError(snapshot.message || "Analysis failed.");
      closeStream();
    }
  }

  function connectStatus(repoId: string): void {
    closeStream();
    reconnectRef.current = 0;
    const stream = new EventSource(`/api/v1/repos/${encodeURIComponent(repoId)}/status`);
    streamRef.current = stream;

    stream.addEventListener("progress", (event) => {
      reconnectRef.current = 0;
      const payload = JSON.parse(event.data) as RepoStatusSnapshot;
      applySnapshot(payload, repoId);
    });

    stream.addEventListener("done", (event) => {
      const payload = JSON.parse(event.data) as RepoStatusSnapshot;
      applySnapshot(payload, repoId);
      setProgress(100);
    });

    stream.addEventListener("error", async (event: Event) => {
      if (isTerminal(stageRef.current)) {
        closeStream();
        return;
      }
      closeStream();
      reconnectRef.current += 1;
      try {
        await reconcileStatus(repoId);
      } catch {
        // ignore and retry below
      }
      if (reconnectRef.current <= 5 && !isTerminal(stageRef.current)) {
        window.setTimeout(() => connectStatus(repoId), reconnectRef.current * 1000);
      } else if (!isTerminal(stageRef.current)) {
        setError("Status stream disconnected after retries.");
      }
      if (event.type === "error" && isTerminal(stageRef.current)) {
        closeStream();
      }
    });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    closeStream();
    setPending(true);
    setError(null);
    setDoneMessage(null);
    setResult(null);
    setStage("queued");
    setProgress(0);
    setCacheHit(false);

    try {
      const payload = await postAnalyze({ github_url: url.trim() });
      setResult(payload);
      setStage(payload.status || "queued");
      setCacheHit(payload.cache_hit);
      connectStatus(payload.repo_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Analyze request failed";
      setError(message);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Analyze Repository</h2>
        <p className="muted">Submit a GitHub URL and follow parse/embed/analyze progress.</p>
        <form className="grid" onSubmit={onSubmit}>
          <label htmlFor="github-url">GitHub URL</label>
          <input
            id="github-url"
            className="input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            required
          />
          <div className="row">
            <button type="submit" className="button" disabled={pending}>
              {pending ? "Submitting..." : "Analyze"}
            </button>
          </div>
        </form>
      </article>

      {error && (
        <article className="error">
          <strong>Analyze failed:</strong> {error}
        </article>
      )}

      {result && (
        <article className="notice">
          <div>
            <strong>Job:</strong> <span className="mono">{result.job_id}</span>
          </div>
          <div>
            <strong>Repo:</strong> <span className="mono">{result.repo_id}</span>
          </div>
          <div>
            <strong>Status:</strong> {stage}
          </div>
          <div>
            <strong>Progress:</strong> {progress}%
          </div>
          <div>
            <strong>Cache hit:</strong> {String(cacheHit)}
          </div>
          <div className="row">
            <Link href={`/dashboard/${encodeURIComponent(result.repo_id)}`}>Open dashboard</Link>
          </div>
          {doneMessage && <div>{doneMessage}</div>}
        </article>
      )}
    </section>
  );
}
