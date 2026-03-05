export type AnalyzeRequest = {
  github_url: string;
};

export type AnalyzeResponse = {
  job_id: string;
  repo_id: string;
  status: string;
  cache_hit: boolean;
  commit_sha: string;
};

export type DashboardResponse = {
  repo_id: string;
  full_name: string;
  github_url: string;
  default_branch: string;
  latest_commit_sha: string;
  quality_score: number;
  architecture_summary: string;
  contributor_stats: Record<string, unknown>;
  tech_debt_flags: Record<string, unknown>;
  file_tree: Record<string, unknown>;
};

export type RepoStatusSnapshot = {
  stage: string;
  progress: number;
  code?: string;
  message?: string;
};

const defaultApiBase = "http://localhost:8000";

export function getBackendBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL || defaultApiBase).replace(/\/+$/, "");
}

export function getApiBase(): string {
  return getBackendBase();
}

async function assertJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      payload?.error?.message ||
      payload?.detail ||
      `${fallbackMessage} (status ${response.status})`;
    throw new Error(message);
  }
  return payload as T;
}

export async function postAnalyze(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  const response = await fetch("/api/v1/repos/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  return assertJson<AnalyzeResponse>(response, "Analyze request failed");
}

export async function getDashboard(repoId: string): Promise<DashboardResponse> {
  const response = await fetch(`/api/v1/repos/${encodeURIComponent(repoId)}/dashboard`, {
    cache: "no-store"
  });
  return assertJson<DashboardResponse>(response, "Dashboard request failed");
}

export async function getRepoStatusOnce(repoId: string): Promise<RepoStatusSnapshot | null> {
  const response = await fetch(`/api/v1/repos/${encodeURIComponent(repoId)}/status?once=true`, {
    headers: { Accept: "text/event-stream" },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`Status request failed (status ${response.status})`);
  }
  const text = await response.text();
  let eventName = "progress";
  let data = "";
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data += line.slice(5).trim();
    }
  }
  if (!data) {
    return null;
  }
  const payload = JSON.parse(data) as RepoStatusSnapshot;
  if (eventName === "error" && !payload.stage) {
    payload.stage = "failed";
  }
  return payload;
}
