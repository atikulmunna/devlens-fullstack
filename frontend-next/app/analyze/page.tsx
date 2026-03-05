"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { postAnalyze } from "@/lib/api";

type AnalyzeState = {
  job_id: string;
  repo_id: string;
  status: string;
  cache_hit: boolean;
};

export default function AnalyzePage() {
  const [url, setUrl] = useState("https://github.com/psf/requests");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeState | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setResult(null);
    try {
      const payload = await postAnalyze({ github_url: url.trim() });
      setResult(payload);
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
        <h2>Analyze</h2>
        <p className="muted">Submit a public repository URL to create an analysis job.</p>
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
          <strong>Request failed:</strong> {error}
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
            <strong>Status:</strong> {result.status}
          </div>
          <div>
            <strong>Cache hit:</strong> {String(result.cache_hit)}
          </div>
          <div>
            <Link href={`/dashboard/${encodeURIComponent(result.repo_id)}`}>Open dashboard shell</Link>
          </div>
        </article>
      )}
    </section>
  );
}
