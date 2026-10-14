import { describe, expect, it } from "vitest";

import { analyzeSteps } from "./analyze-steps";

const states = (stage: string, failedStage: string | null = null) =>
  analyzeSteps(stage, failedStage, null).map((step) => step.state);

describe("analyzeSteps", () => {
  it("shows every step waiting while the job is queued", () => {
    expect(states("queued")).toEqual(["waiting", "waiting", "waiting", "waiting"]);
  });

  it("marks earlier steps done and the running one current", () => {
    expect(states("cloning")).toEqual(["current", "waiting", "waiting", "waiting"]);
    expect(states("embedding")).toEqual(["done", "done", "current", "waiting"]);
    expect(states("done")).toEqual(["done", "done", "done", "done"]);
  });

  it("marks the step that was running as failed", () => {
    expect(states("failed", "parsing")).toEqual(["done", "failed", "waiting", "waiting"]);
  });

  it("puts a failure with no known running step on the first step", () => {
    expect(states("failed", null)).toEqual(["failed", "waiting", "waiting", "waiting"]);
    expect(states("failed", "queued")).toEqual(["failed", "waiting", "waiting", "waiting"]);
  });

  it("counts indexed sections while indexing and summarizes them afterwards", () => {
    const counts = { files: 1, chunks: 1204, indexedChunks: 320 };

    const indexing = analyzeSteps("embedding", null, counts);
    expect(indexing[1].detail).toBe("1 file, 1,204 code sections");
    expect(indexing[2].detail).toBe("320 of 1,204 sections");

    const finished = analyzeSteps("done", null, { ...counts, indexedChunks: 1204 });
    expect(finished[2].detail).toBe("1,204 sections searchable");
    expect(finished[0].detail).toBeNull();
    expect(finished[3].detail).toBeNull();
  });

  it("shows no counts before parsing has produced any", () => {
    expect(analyzeSteps("embedding", null, { files: 0, chunks: 0, indexedChunks: 0 })[1].detail).toBeNull();
    expect(analyzeSteps("embedding", null, null)[2].detail).toBeNull();
  });
});
