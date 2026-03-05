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

const apiBase = process.env.NEXT_PUBLIC_API_URL;

export function getApiBase(): string {
  return (apiBase || "http://localhost:8000").replace(/\/+$/, "");
}

export async function postAnalyze(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  const response = await fetch(`${getApiBase()}/api/v1/repos/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`Analyze failed with status ${response.status}`);
  }
  return (await response.json()) as AnalyzeResponse;
}

export async function getDashboard(repoId: string): Promise<DashboardResponse> {
  const response = await fetch(`${getApiBase()}/api/v1/repos/${encodeURIComponent(repoId)}/dashboard`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`Dashboard request failed with status ${response.status}`);
  }
  return (await response.json()) as DashboardResponse;
}
