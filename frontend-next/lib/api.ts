import { authFetch } from "./auth";

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

// Mirrors DashboardResponse in backend/app/api/v1/repos.py.
export type DashboardRepository = {
  id: string;
  github_url: string;
  full_name: string;
  owner: string;
  name: string;
  default_branch: string;
  latest_commit_sha: string | null;
  description: string | null;
  stars: number | null;
  forks: number | null;
  language: string | null;
  size_kb: number | null;
};

export type DashboardAnalysis = {
  quality_score: number | null;
  architecture_summary: string | null;
  language_breakdown: Record<string, number> | null;
  contributor_stats: Record<string, unknown> | null;
  tech_debt_flags: Record<string, unknown> | null;
  file_tree: Record<string, unknown> | null;
  created_at: string;
};

export type DashboardResponse = {
  repo_id: string;
  repository: DashboardRepository;
  analysis: DashboardAnalysis | null;
  has_analysis: boolean;
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

// --- Chat --------------------------------------------------------------------

export type ChatCitation = {
  file_path?: string;
  line_start?: number;
  line_end?: number;
  score?: number;
  [key: string]: unknown;
};

export type ChatDoneMeta = {
  message_id: string;
  citations: ChatCitation[];
  no_citation: boolean;
};

export type CreateSessionResponse = {
  session_id: string;
  repo_id: string;
  created_at: string;
};

export async function createChatSession(repoId: string): Promise<CreateSessionResponse> {
  const response = await authFetch("/api/v1/chat/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_id: repoId })
  });
  return assertJson<CreateSessionResponse>(response, "Could not start chat session");
}

export async function getSuggestions(repoId: string): Promise<string[]> {
  const response = await authFetch(`/api/v1/chat/repos/${encodeURIComponent(repoId)}/suggestions`);
  const payload = await assertJson<{ suggestions: string[] }>(response, "Could not load suggestions");
  return payload.suggestions || [];
}

export type ChatStreamHandlers = {
  onToken: (token: string) => void;
  onDone: (meta: ChatDoneMeta) => void;
};

export async function sendChatMessageStream(
  sessionId: string,
  content: string,
  topK: number,
  handlers: ChatStreamHandlers
): Promise<void> {
  const response = await authFetch(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content, top_k: topK })
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null);
    const message =
      payload?.error?.message || payload?.detail || `Chat request failed (status ${response.status})`;
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";

  // Parse the SSE stream line by line, keeping any trailing partial line buffered.
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        if (!data) {
          continue;
        }
        try {
          const payload = JSON.parse(data);
          if (eventName === "delta" && typeof payload.token === "string") {
            handlers.onToken(payload.token);
          } else if (eventName === "done") {
            handlers.onDone(payload as ChatDoneMeta);
          }
        } catch {
          // ignore malformed SSE chunk
        }
      }
    }
  }
}

// --- Commit-diff intelligence ------------------------------------------------

export type DiffChangedFile = {
  path: string;
  status: string;
  added: number;
  removed: number;
  hunks: number;
};

export type SecurityFlag = { path: string; categories: string[] };

export type BlastRadius = {
  changed_files: string[];
  impacted_files: string[];
  impacted_count: number;
};

export type CommitDiffSummary = {
  repo_id: string;
  base_sha: string | null;
  head_sha: string;
  changed_files: DiffChangedFile[];
  security_flags: SecurityFlag[];
  blast_radius: BlastRadius;
  created_at: string | null;
};

export async function getCommitDiff(repoId: string, head?: string): Promise<CommitDiffSummary> {
  const suffix = head ? `?head=${encodeURIComponent(head)}` : "";
  const response = await authFetch(`/api/v1/repos/${encodeURIComponent(repoId)}/diff${suffix}`);
  return assertJson<CommitDiffSummary>(response, "Could not load commit diff");
}

export async function askAboutDiffStream(
  repoId: string,
  question: string,
  handlers: ChatStreamHandlers
): Promise<void> {
  const response = await authFetch(`/api/v1/repos/${encodeURIComponent(repoId)}/diff/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question })
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null);
    const message =
      payload?.error?.message || payload?.detail || `Diff question failed (status ${response.status})`;
    throw new Error(message);
  }
  await readSseStream(response.body.getReader(), handlers);
}

async function readSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: ChatStreamHandlers
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        if (!data) {
          continue;
        }
        try {
          const payload = JSON.parse(data);
          if (eventName === "delta" && typeof payload.token === "string") {
            handlers.onToken(payload.token);
          } else if (eventName === "done") {
            handlers.onDone(payload as ChatDoneMeta);
          }
        } catch {
          // ignore malformed SSE chunk
        }
      }
    }
  }
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
