"use client";

import { FormEvent, useState } from "react";
import { AnalyzeStatus } from "@/components/analyze-status";
import { useAnalyzeJob } from "@/lib/use-analyze-job";

export default function AnalyzePage() {
  const [url, setUrl] = useState("");
  const { start, pending, error, job, stage, progress } = useAnalyzeJob();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void start(url);
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Analyze a repository</h2>
        <p className="muted">Paste a public GitHub repository. Progress shows here until it is ready.</p>
        <form className="grid" onSubmit={onSubmit}>
          <label htmlFor="github-url">Repository URL</label>
          <input
            id="github-url"
            className="input mono"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            required
          />
          <div className="row">
            <button type="submit" className="button" disabled={pending}>
              {pending ? "Starting..." : "Analyze repository"}
            </button>
          </div>
        </form>
        <AnalyzeStatus job={job} stage={stage} progress={progress} error={error} />
      </article>
    </section>
  );
}
