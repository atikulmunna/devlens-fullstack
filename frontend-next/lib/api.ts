import type { components } from "./api-schema";
import { authFetch } from "./auth";
import { ApiError } from "./errors";

// Request and response shapes come from the backend's OpenAPI schema (lib/api-schema.ts, generated
// by `npm run gen:api` from lib/openapi.json), so a backend change that breaks the frontend fails
// typecheck. Only shapes the schema cannot describe (SSE events, JSON columns) are written here.
type Schemas = components["schemas"];

// Fields with a server default are generated as always present, which is right for responses; in
// a request they may be left out.
export type AnalyzeRequest = Pick<Schemas["AnalyzeRepoRequest"], "github_url"> & Partial<Schemas["AnalyzeRepoRequest"]>;
export type AnalyzeResponse = Schemas["AnalyzeRepoResponse"];

export type LongFunction = {
  file: string;
  name: string;
  line: number;
  length: number;
};

// Code health measured while parsing. Analyses from before that have none of these fields.
export type TechDebtFlags = {
  measured?: boolean;
  long_function_lines?: number;
  long_function_count?: number;
  long_functions?: LongFunction[];
  todo_count?: number;
  todo_file_count?: number;
  test_file_count?: number;
};

// Contributors from the GitHub API; `error` is set when GitHub could not be reached.
export type ContributorStats = {
  top_contributors?: { username: string; commits: number }[];
  error?: string;
};

// The file tree as the analyze worker writes it: one entry per indexed path.
export type FileTreeFlags = {
  files?: Record<string, { chunks: number; lines: number; language: string }>;
};

export type LanguageShare = Schemas["LanguageShareResponse"];
export type DependencyGraph = Schemas["DependencyGraphResponse"];

// These three are JSON columns; the types are the shapes the analyze worker writes.
export type DashboardAnalysis = Omit<
  Schemas["DashboardAnalysisResponse"],
  "tech_debt_flags" | "contributor_stats" | "file_tree"
> & {
  tech_debt_flags: TechDebtFlags | null;
  contributor_stats: ContributorStats | null;
  file_tree: FileTreeFlags | null;
};

export type DashboardResponse = Omit<Schemas["DashboardResponse"], "analysis"> & {
  analysis: DashboardAnalysis | null;
};

export type RepoStatusSnapshot = {
  stage: string;
  progress: number;
  code?: string;
  message?: string;
  // Present once parsing has finished.
  files?: number;
  chunks?: number;
  indexed_chunks?: number;
};

const defaultApiBase = "http://localhost:8000";

export function getBackendBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL || defaultApiBase).replace(/\/+$/, "");
}

async function errorFrom(response: Response, fallbackMessage: string): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  const message = payload?.error?.message || payload?.detail || `${fallbackMessage} (status ${response.status})`;
  const retryAfter = Number(response.headers.get("Retry-After"));
  return new ApiError(message, response.status, Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null);
}

async function assertJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    throw await errorFrom(response, fallbackMessage);
  }
  return (await response.json()) as T;
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

export type RepoSummary = Schemas["RepoSummaryResponse"];

// null when DevLens has never analyzed the repository (the page then offers to analyze it).
export async function getRepoByName(owner: string, name: string): Promise<RepoSummary | null> {
  const response = await fetch(
    `/api/v1/repos/by-name/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`,
    { cache: "no-store" }
  );
  if (response.status === 404) {
    return null;
  }
  return assertJson<RepoSummary>(response, "Could not load the repository");
}

export async function getRecentRepos(limit = 6): Promise<RepoSummary[]> {
  const response = await fetch(`/api/v1/repos/recent?limit=${limit}`, { cache: "no-store" });
  const payload = await assertJson<Schemas["RecentReposResponse"]>(response, "Could not load recent repositories");
  return payload.repos;
}

export async function getDependencyGraph(repoId: string): Promise<DependencyGraph> {
  const response = await fetch(`/api/v1/repos/${encodeURIComponent(repoId)}/dependency-graph`, {
    cache: "no-store"
  });
  return assertJson<DependencyGraph>(response, "Could not load the import graph");
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
  // The context's number in the prompt; the answer cites it as [ref].
  ref?: number;
  cited?: boolean;
  [key: string]: unknown;
};

export type ChatDoneMeta = {
  message_id: string;
  citations: ChatCitation[];
  no_citation: boolean;
  // The commit the cited lines come from; links to them stay valid after a re-analysis.
  commit_sha?: string | null;
};

export type ChatSessionSummary = Schemas["ChatSessionListItem"];
export type ChatSessionDetail = Schemas["ChatSessionResponse"];

export async function listChatSessions(repoId: string): Promise<ChatSessionSummary[]> {
  const response = await authFetch(`/api/v1/chat/sessions?repo_id=${encodeURIComponent(repoId)}`);
  const payload = await assertJson<Schemas["ChatSessionListResponse"]>(response, "Could not load earlier chats");
  return payload.sessions ?? [];
}

export async function getChatSession(sessionId: string): Promise<ChatSessionDetail> {
  const response = await authFetch(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`);
  return assertJson<ChatSessionDetail>(response, "Could not load the chat");
}

export type CreateSessionResponse = Schemas["CreateChatSessionResponse"];

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
  const payload = await assertJson<Schemas["SuggestedQuestionsResponse"]>(response, "Could not load suggestions");
  return payload.suggestions || [];
}

// --- Streaming answers (chat and diff questions) ------------------------------

export type StreamHandlers<TDone> = {
  onToken: (token: string) => void;
  onDone: (meta: TDone) => void;
};

// Reads `delta` and `done` events from an SSE body, keeping a trailing partial line buffered
// until the next chunk completes it. Malformed events are skipped.
export async function readSseStream<TDone>(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: StreamHandlers<TDone>
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
        continue;
      }
      const data = line.startsWith("data:") ? line.slice(5).trim() : "";
      if (!data) {
        continue;
      }
      try {
        const payload = JSON.parse(data);
        if (eventName === "delta" && typeof payload.token === "string") {
          handlers.onToken(payload.token);
        } else if (eventName === "done") {
          handlers.onDone(payload as TDone);
        }
      } catch {
        // A malformed event is skipped; the rest of the stream still renders.
      }
    }
  }
}

async function postSseStream<TDone>(
  url: string,
  body: unknown,
  failureLabel: string,
  handlers: StreamHandlers<TDone>,
  signal?: AbortSignal
): Promise<void> {
  const response = await authFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal
  });
  if (!response.ok || !response.body) {
    throw await errorFrom(response, failureLabel);
  }
  await readSseStream(response.body.getReader(), handlers);
}

// `signal` stops the answer mid-stream (the Stop button); the reader then throws an AbortError.
export function sendChatMessageStream(
  sessionId: string,
  content: string,
  topK: number,
  handlers: StreamHandlers<ChatDoneMeta>,
  signal?: AbortSignal
): Promise<void> {
  const url = `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/message`;
  return postSseStream(url, { content, top_k: topK }, "Chat request failed", handlers, signal);
}

// --- Commit-diff intelligence ------------------------------------------------

export type CommitDiffSummary = Schemas["CommitDiffResponse"];

export type CommitDiffEntry = Schemas["CommitDiffEntry"];
export type ChangedFile = CommitDiffSummary["changed_files"][number];
export type SecurityFlag = CommitDiffSummary["security_flags"][number];

export async function listCommitDiffs(repoId: string): Promise<CommitDiffEntry[]> {
  const response = await authFetch(`/api/v1/repos/${encodeURIComponent(repoId)}/diffs`);
  const payload = await assertJson<Schemas["CommitDiffListResponse"]>(response, "Could not load analyzed commits");
  return payload.diffs;
}

export async function getCommitDiff(repoId: string, head?: string): Promise<CommitDiffSummary> {
  const suffix = head ? `?head=${encodeURIComponent(head)}` : "";
  const response = await authFetch(`/api/v1/repos/${encodeURIComponent(repoId)}/diff${suffix}`);
  return assertJson<CommitDiffSummary>(response, "Could not load commit diff");
}

export type DiffDoneMeta = {
  head_sha: string;
  base_sha: string | null;
  security_categories: string[];
};

export function askAboutDiffStream(
  repoId: string,
  question: string,
  handlers: StreamHandlers<DiffDoneMeta>,
  head?: string
): Promise<void> {
  const suffix = head ? `?head=${encodeURIComponent(head)}` : "";
  const url = `/api/v1/repos/${encodeURIComponent(repoId)}/diff/ask${suffix}`;
  return postSseStream(url, { question }, "Diff question failed", handlers);
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
