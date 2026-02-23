# DevLens — AI-Powered GitHub Repository Analyzer
## Software Requirements & Specification Document

**Version:** 1.1  
**Author:** Atikul Islam Munna  
**Date:** February 23, 2026  
**Status:** Draft

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Goals & Success Criteria](#2-goals--success-criteria)
3. [System Architecture](#3-system-architecture)
4. [Feature Specification](#4-feature-specification)
5. [Workflow & Data Flow](#5-workflow--data-flow)
6. [Tech Stack](#6-tech-stack)
7. [Database Schema](#7-database-schema)
8. [API Design](#8-api-design)
9. [Frontend Pages & Components](#9-frontend-pages--components)
10. [Task Breakdown & Milestones](#10-task-breakdown--milestones)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [Deployment Plan](#12-deployment-plan)
13. [Architecture Decisions (v1.1)](#13-architecture-decisions-v11)

---

## 1. Project Overview

**DevLens** is a full-stack web application that allows developers to analyze any public GitHub repository using AI. A user pastes a GitHub URL, and DevLens processes the codebase to produce a rich, interactive dashboard — including architecture summaries, code quality insights, contributor analytics, tech debt detection, and a conversational AI interface to query the codebase directly.

### Problem Statement

Developers frequently need to onboard into unfamiliar repositories, audit codebases for quality, or understand architectural decisions quickly. Existing tools (GitHub's native UI, SonarQube, CodeClimate) either lack AI-driven insights, require complex setup, or don't support ad-hoc exploration. DevLens provides instant, zero-setup intelligence over any public repo.

### Core Value Proposition

- **Instant onboarding:** Understand a new codebase in minutes, not days.
- **AI chat over code:** Ask questions like "where is authentication handled?" or "what does the payment module do?"
- **Visual analytics:** Contributor heatmaps, commit frequency, language breakdown, dependency graphs.
- **Tech debt radar:** Automatically surface duplicated logic, long functions, missing tests, and outdated dependencies.

---

## 2. Goals & Success Criteria

### Primary Goals

- Allow any user to analyze a public GitHub repo by pasting its URL.
- Deliver analysis results within 2–3 minutes for repos up to 50,000 lines of code.
- Provide a functional AI chat interface backed by a RAG pipeline over the indexed codebase.
- Ship a production-quality frontend with real UI (not Streamlit/Gradio).

### Success Criteria

| Metric | Target |
|---|---|
| Repo processing time (≤50k LOC) | < 3 minutes |
| RAG answer relevance (manual eval) | > 80% accurate responses |
| UI responsiveness | < 200ms for dashboard interactions |
| Uptime | > 99% on free-tier hosting |
| Test coverage (backend) | > 70% |

### Out of Scope (v1)

- Private repository analysis (requires OAuth token scope management — v2 feature).
- Real-time collaborative sessions.
- IDE plugin integrations.
- Support for non-GitHub platforms (GitLab, Bitbucket).
- Full multi-language deep static analysis parity across all major languages (v1 will prioritize Python + TypeScript/JavaScript).

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Next.js)                         │
│  Landing → Analyze → Dashboard → File Tree → Chat Interface     │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS REST / SSE
┌────────────────────────────▼────────────────────────────────────┐
│                      API GATEWAY (FastAPI)                       │
│   /api/v1/repos  |  /api/v1/analysis  |  /api/v1/chat           │
└──────┬─────────────────────┬──────────────────────┬─────────────┘
       │                     │                      │
┌──────▼──────┐   ┌──────────▼────────┐   ┌────────▼────────────┐
│  GitHub     │   │  Job Queue        │   │  RAG Engine         │
│  Ingestion  │   │  (Redis + RQ)     │   │  (Qdrant +          │
│  Service    │   │                   │   │   sentence-          │
│             │   │  Workers:         │   │   transformers)     │
│  - Clone    │   │  - parse_worker   │   │                     │
│  - Filter   │   │  - embed_worker   │   │  - Hybrid search    │
│  - Chunk    │   │  - analyze_worker │   │  - Reranking        │
└──────┬──────┘   └──────────┬────────┘   └────────┬────────────┘
       │                     │                      │
┌──────▼─────────────────────▼──────────────────────▼────────────┐
│                        DATA LAYER                                │
│   PostgreSQL (metadata, analysis results, users, sessions)      │
│   Qdrant (code embeddings, chunk vectors)                       │
│   Redis (job queue, session cache, rate limiting)               │
│   Cloudflare R2 (cloned repo storage, report exports)           │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**GitHub Ingestion Service** — Clones repo via GitHub API (or git), filters relevant files by extension, splits code into semantic chunks, and dispatches jobs to the worker queue.

**Job Queue (Redis + RQ)** — Three specialized workers handle the async pipeline: parsing & chunking, embedding & indexing, and static analysis. Progress is streamed back to the client via Server-Sent Events (SSE).

**RAG Engine** — Indexes code chunks into Qdrant using `sentence-transformers`. At query time, performs hybrid retrieval (vector + PostgreSQL full-text keyword search), reranks results, and synthesizes answers via an LLM (OpenRouter/Groq).

**FastAPI Backend** — Exposes REST endpoints, handles GitHub OAuth, manages job state, and proxies SSE progress updates.

**Next.js Frontend** — Renders the analysis dashboard with interactive charts, a file tree explorer, and a chat interface with streaming responses.

### Key Architecture Clarifications (v1.1)

- Auth source of truth is **FastAPI JWT sessions**. Frontend does not issue its own auth tokens.
- Qdrant storage model uses a **single collection** (`devlens_code_chunks`) with mandatory payload filter by `repo_id`.
- Keyword retrieval uses **PostgreSQL full-text search** (`tsvector` + `ts_rank_cd`), not strict BM25.
- Cache validity is keyed by `repo_full_name + default_branch + commit_sha`.

---

## 4. Feature Specification

### 4.1 Repository Ingestion

| Feature | Description |
|---|---|
| URL input | Accept `https://github.com/user/repo` format, validate existence via GitHub API |
| File filtering | Index only source files (`.py`, `.js`, `.ts`, `.go`, `.java`, `.cpp`, etc.), skip binaries, `node_modules`, `.git` |
| Size limits | Reject repos > 200MB or > 500k LOC with a clear error message |
| Caching | If same `repo + commit_sha` was analyzed in last 24 hours, return cached results |
| Progress tracking | SSE stream: `cloning → parsing → embedding → analyzing → done` |
| Idempotency | `POST /repos/analyze` accepts idempotency key; duplicate submissions return existing active/completed job |
| Stage safeguards | Clone timeout 60s, max 8,000 files, max 20,000 chunks, per-stage timeout with explicit failure reason |

### 4.2 Analysis Dashboard

| Panel | Description |
|---|---|
| **Overview Card** | Language breakdown pie chart, repo stats (stars, forks, open issues, last commit) |
| **Architecture Summary** | AI-generated 3–5 paragraph description of the repo's purpose, structure, and design patterns |
| **File Tree Explorer** | Interactive file tree with per-file complexity scores and quick-view metadata |
| **Contributor Analytics** | Commit heatmap by contributor, lines added/removed over time, top contributors bar chart |
| **Tech Debt Radar** | Flagged files: long functions (>50 lines), high cyclomatic complexity, TODO/FIXME count, test coverage estimate |
| **Code Quality Score** | Composite score (0–100) based on test presence, documentation ratio, complexity, and duplication |

**v1 scope note:** Dependency graph moves to v1.1 unless core panels are complete and stable.

### 4.3 AI Chat Interface

| Feature | Description |
|---|---|
| Context-aware Q&A | RAG pipeline retrieves relevant code chunks and answers questions about the codebase |
| Streaming responses | LLM response streamed token-by-token via SSE |
| Source citations | Every answer links to the specific files/lines that informed it |
| Suggested questions | Auto-generated starter questions based on repo content (e.g., "How is authentication implemented?") |
| Conversation history | Full session history stored per user, resumable |
| Code highlighting | Code snippets in responses rendered with syntax highlighting |

### 4.4 Authentication & User Management

| Feature | Description |
|---|---|
| GitHub OAuth | Login with GitHub using OAuth 2.0 |
| Guest mode | Allow up to 3 analyses without login (rate-limited by IP) |
| User dashboard | History of analyzed repos, saved chat sessions, export options |

**v1 scope note:** API key issuance moves to v1.1.

### 4.5 Export & Sharing

| Feature | Description |
|---|---|
| Report export | Download full analysis as Markdown, HTML, or PDF |
| Shareable link | Generate a public permalink to a specific analysis |
| Embed badge | Markdown badge showing repo's DevLens quality score |

---

## 5. Workflow & Data Flow

### 5.1 Repo Analysis Pipeline

```
User submits URL
      │
      ▼
[Validate URL] ──── Invalid ──→ Return 400 error
      │
      ▼
[Check Cache by commit_sha] ──── Hit ──→ Return cached analysis instantly
      │ Miss
      ▼
[Create Job Record in PostgreSQL + idempotency lock]
      │
      ▼
[Dispatch to Redis Queue]
      │
      ├──→ parse_worker
      │         │ Clone repo (shallow, depth=1)
      │         │ Enforce clone timeout and repo-size guardrails
      │         │ Walk file tree
      │         │ Filter by extension whitelist
      │         │ Split into chunks (512 tokens, 50-token overlap)
      │         │ Store chunks in PostgreSQL
      │         └──→ Emit SSE: "parsing complete"
      │
      ├──→ embed_worker
      │         │ Load chunks from PostgreSQL
      │         │ Generate embeddings (sentence-transformers)
      │         │ Upsert vectors into Qdrant collection
      │         └──→ Emit SSE: "indexing complete"
      │
      └──→ analyze_worker
                │ Run static analysis (AST parsing per language)
                │ Compute complexity scores
                │ Call LLM for architecture summary
                │ Aggregate contributor stats via GitHub API
                │ Store results in PostgreSQL
                └──→ Emit SSE: "analysis complete"
      │
      ▼
[Frontend renders dashboard from REST endpoints]
```

### 5.2 Chat Query Flow

```
User sends message
      │
      ▼
[FastAPI /chat endpoint]
      │
      ▼
[Query Qdrant: dense vector search]
      │
      ▼
[Query PostgreSQL: full-text keyword search over chunk text]
      │
      ▼
[Merge & rerank results (cross-encoder)]
      │
      ▼
[Build prompt: system context + top-k chunks + conversation history]
      │
      ▼
[Stream LLM response via OpenRouter/Groq]
      │
      ▼
[Return streamed tokens + source citations to frontend]
```

Retrieval implementation detail: PostgreSQL uses `to_tsvector` + `plainto_tsquery` + `ts_rank_cd` for lexical ranking.

### 5.3 User Authentication Flow

```
User clicks "Login with GitHub"
      │
      ▼
[Redirect to GitHub OAuth]
      │
      ▼
[GitHub returns auth code]
      │
      ▼
[FastAPI exchanges code for access token]
      │
      ▼
[Fetch user profile from GitHub API]
      │
      ▼
[Create/update user record in PostgreSQL]
      │
      ▼
[Issue JWT (access token 15min + refresh token 7days)]
      │
      ▼
[Store refresh token in HttpOnly cookie]
```

Frontend auth integration detail: Next.js uses backend-issued JWT and refresh cookie via secure API calls; no second token authority in frontend.

---

## 6. Tech Stack

### Backend

| Layer | Technology | Justification |
|---|---|---|
| API Framework | FastAPI | Async support, automatic OpenAPI docs, familiar from existing projects |
| Job Queue | Redis + RQ | Lightweight, Redis already in your stack, simpler than Kafka for this scale |
| Vector DB | Qdrant | Already used in SAG-RAG; ideal for code chunk search |
| Relational DB | PostgreSQL | Job state, user data, analysis metadata |
| ORM | SQLAlchemy + Alembic | Type-safe queries, migration support |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Fast, lightweight, good semantic quality |
| LLM | OpenRouter (primary) / Groq (fallback) | Cost-effective, model-agnostic |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Improves RAG precision |
| Auth | PyJWT + GitHub OAuth 2.0 | Single auth authority in backend |
| Cache | Redis | Analysis result cache, session cache |
| Storage | Cloudflare R2 | Report exports, cloned repo temp storage |
| Observability | Prometheus + OpenTelemetry | Metrics and tracing |
| Testing | Pytest + httpx | Unit and integration tests |
| Containerization | Docker + Docker Compose | Local dev and deployment parity |

### Frontend

| Layer | Technology | Justification |
|---|---|---|
| Framework | Next.js 14 (App Router) | SSR/SSG, API routes, production-ready |
| Language | TypeScript | Type safety, better DX |
| Styling | Tailwind CSS | Fast, consistent styling |
| UI Components | shadcn/ui | High-quality, accessible components |
| Charts | Recharts | Declarative, React-native charting |
| Graph Visualization | React Flow | Dependency graph rendering |
| Code Highlighting | Shiki | Accurate, VS Code-quality highlighting |
| State Management | Zustand | Lightweight, no boilerplate |
| Data Fetching | TanStack Query | Caching, background refetch, loading states |
| SSE Client | EventSource API (native) | Progress streaming from backend |
| Auth | Backend JWT session client | Frontend uses backend auth endpoints and HttpOnly refresh flow |

### DevOps & Deployment

| Tool | Purpose |
|---|---|
| Railway | Backend deployment (FastAPI + workers) |
| Vercel | Frontend deployment (Next.js) |
| Supabase | Managed PostgreSQL |
| Qdrant Cloud | Managed vector database (free tier) |
| Upstash | Managed Redis (free tier) |
| GitHub Actions | CI/CD pipeline |
| Docker Hub | Container registry |

---

## 7. Database Schema

### PostgreSQL Tables

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_id INTEGER UNIQUE NOT NULL,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Repositories
CREATE TABLE repositories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_url TEXT UNIQUE NOT NULL,
    full_name VARCHAR(255) UNIQUE NOT NULL, -- owner/name
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    default_branch VARCHAR(255) DEFAULT 'main',
    latest_commit_sha VARCHAR(64),
    description TEXT,
    stars INTEGER,
    forks INTEGER,
    language VARCHAR(100),
    size_kb INTEGER,
    last_analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Analysis Jobs
CREATE TABLE analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID REFERENCES repositories(id),
    user_id UUID REFERENCES users(id),
    idempotency_key VARCHAR(255),
    commit_sha VARCHAR(64),
    status VARCHAR(50) DEFAULT 'queued',  -- queued, cloning, parsing, embedding, analyzing, done, failed
    progress INTEGER DEFAULT 0,           -- 0-100
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Analysis Results
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID REFERENCES repositories(id),
    job_id UUID REFERENCES analysis_jobs(id),
    architecture_summary TEXT,
    quality_score INTEGER,
    language_breakdown JSONB,
    contributor_stats JSONB,
    tech_debt_flags JSONB,
    file_tree JSONB,
    cache_key VARCHAR(512) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Code Chunks (for RAG metadata)
CREATE TABLE code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID REFERENCES repositories(id),
    file_path TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    content TEXT NOT NULL,
    language VARCHAR(50),
    qdrant_point_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_code_chunks_repo_path ON code_chunks(repo_id, file_path);
CREATE INDEX idx_analysis_jobs_repo_status ON analysis_jobs(repo_id, status);

-- Lexical retrieval support (PostgreSQL FTS)
ALTER TABLE code_chunks ADD COLUMN fts tsvector;
CREATE INDEX idx_code_chunks_fts ON code_chunks USING GIN (fts);

-- Chat Sessions
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID REFERENCES repositories(id),
    user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat Messages
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id),
    role VARCHAR(20) NOT NULL,  -- user, assistant
    content TEXT NOT NULL,
    source_citations JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Qdrant Collection Schema

```json
{
  "collection": "devlens_code_chunks",
  "vectors": { "size": 384, "distance": "Cosine" },
  "payload_schema": {
    "repo_id": "string",
    "file_path": "string",
    "start_line": "integer",
    "end_line": "integer",
    "language": "string",
    "chunk_id": "string"
  }
}
```

Query rule: every vector search request must include filter `{ "must": [{ "key": "repo_id", "match": { "value": "<repo_id>" } }] }`.

---

## 8. API Design

### Base URL: `/api/v1`

#### Repository Endpoints

```
POST   /repos/analyze          Submit a repo URL for analysis
GET    /repos/{repo_id}        Get repo metadata
GET    /repos/{repo_id}/status  Get job status + progress (SSE)
GET    /repos/{repo_id}/results Get full analysis results
GET    /repos/{repo_id}/files  Get file tree with metrics
GET    /repos/history          Get user's analysis history
```

#### Chat Endpoints

```
POST   /chat/sessions           Create a new chat session
GET    /chat/sessions/{id}      Get session with message history
POST   /chat/sessions/{id}/message  Send a message (SSE streaming response)
GET    /chat/sessions/{id}/suggestions  Get suggested starter questions
DELETE /chat/sessions/{id}      Delete a session
```

#### Auth Endpoints

```
GET    /auth/github             Initiate GitHub OAuth flow
GET    /auth/callback           OAuth callback handler
POST   /auth/refresh            Refresh JWT token
DELETE /auth/logout             Invalidate session
GET    /auth/me                 Get current user profile
```

#### Export Endpoints

```
GET    /export/{repo_id}/markdown   Export report as .md
GET    /export/{repo_id}/html       Export report as .html
GET    /export/{repo_id}/pdf        Export report as .pdf
POST   /export/{repo_id}/share      Generate shareable link
```

### Contract Additions (v1.1)

#### `POST /repos/analyze` request

```json
{
  "github_url": "https://github.com/user/repo",
  "force_reanalyze": false
}
```

Headers:

- `Idempotency-Key: <uuid-or-client-generated-key>`

#### `POST /repos/analyze` response

```json
{
  "job_id": "uuid",
  "repo_id": "uuid",
  "status": "queued",
  "cache_hit": false,
  "commit_sha": "abc123..."
}
```

#### SSE event contract: `GET /repos/{repo_id}/status`

```text
event: progress
data: {"job_id":"uuid","stage":"parsing","progress":35,"message":"Chunking files","eta_seconds":62}

event: done
data: {"job_id":"uuid","stage":"done","progress":100}

event: error
data: {"job_id":"uuid","stage":"embedding","code":"EMBED_TIMEOUT","message":"Embedding stage exceeded timeout"}
```

#### Standard error envelope (all endpoints)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid GitHub URL format",
    "details": {}
  }
}
```

### Example Response: Analysis Results

```json
{
  "repo_id": "uuid",
  "repo": {
    "url": "https://github.com/user/repo",
    "name": "repo",
    "stars": 1200,
    "language": "Python"
  },
  "quality_score": 74,
  "architecture_summary": "This repository implements a FastAPI-based REST API...",
  "language_breakdown": {
    "Python": 68.4,
    "TypeScript": 21.2,
    "Shell": 10.4
  },
  "tech_debt": {
    "long_functions": [
      { "file": "src/core/processor.py", "line": 145, "length": 87 }
    ],
    "todo_count": 23,
    "missing_tests": ["src/services/auth.py", "src/utils/parser.py"]
  },
  "contributors": [
    { "username": "user1", "commits": 234, "lines_added": 12450 }
  ]
}
```

---

## 9. Frontend Pages & Components

### Pages

| Route | Description |
|---|---|
| `/` | Landing page — hero section, demo GIF, feature highlights, CTA |
| `/analyze` | URL input form with real-time progress tracker (SSE) |
| `/dashboard/[repoId]` | Full analysis dashboard |
| `/dashboard/[repoId]/chat` | AI chat interface |
| `/dashboard/[repoId]/files` | File tree explorer with per-file metrics |
| `/profile` | User profile and analysis history |
| `/share/[token]` | Public view of a shared analysis |

### Key Components

```
components/
├── layout/
│   ├── Navbar.tsx
│   └── Footer.tsx
├── analyze/
│   ├── RepoInputForm.tsx        # URL input + validation
│   └── ProgressTracker.tsx      # SSE-driven step-by-step progress UI
├── dashboard/
│   ├── OverviewCard.tsx         # Stars, forks, language stats
│   ├── LanguagePieChart.tsx     # Recharts pie chart
│   ├── QualityScoreGauge.tsx    # Radial score display
│   ├── ArchitectureSummary.tsx  # AI-generated text panel
│   ├── TechDebtPanel.tsx        # Flagged files list
│   ├── ContributorHeatmap.tsx   # GitHub-style activity grid
│   └── DependencyGraph.tsx      # React Flow graph
├── filetree/
│   ├── FileTreeExplorer.tsx     # Collapsible tree
│   └── FileMetricsBadge.tsx     # Complexity/score per file
├── chat/
│   ├── ChatInterface.tsx        # Main chat container
│   ├── MessageBubble.tsx        # User/assistant message
│   ├── CodeBlock.tsx            # Shiki syntax highlighted code
│   ├── SourceCitations.tsx      # Linked file references
│   └── SuggestedQuestions.tsx   # Starter question chips
└── shared/
    ├── LoadingSpinner.tsx
    ├── ErrorBoundary.tsx
    └── ExportMenu.tsx
```

---

## 10. Task Breakdown & Milestones

### Phase 1 — Foundation (Week 1–2)

- [ ] Initialize monorepo structure (`/backend`, `/frontend`, `/workers`)
- [ ] Set up Docker Compose for local dev (FastAPI + PostgreSQL + Redis + Qdrant)
- [ ] Implement GitHub OAuth (FastAPI only, backend-issued JWT + refresh cookie)
- [ ] Build database schema and run Alembic migrations
- [ ] Create GitHub ingestion service (clone, filter, chunk)
- [ ] Set up Redis job queue with RQ workers
- [ ] Implement SSE progress streaming endpoint
- [ ] Add idempotency key handling and duplicate job suppression

### Phase 2 — RAG Pipeline (Week 3)

- [ ] Integrate sentence-transformers for chunk embedding
- [ ] Set up Qdrant collection and upsert pipeline
- [ ] Implement hybrid retrieval (Qdrant vector + PostgreSQL FTS)
- [ ] Integrate cross-encoder reranker
- [ ] Connect OpenRouter/Groq for LLM synthesis
- [ ] Build `/chat` endpoints with streaming
- [ ] Add source citation extraction
- [ ] Build golden-repo relevance evaluation set and baseline scoring

### Phase 3 — Static Analysis (Week 4)

- [ ] AST-based complexity analyzer (v1 languages: Python + TypeScript/JavaScript)
- [ ] Tech debt detector (long functions, TODO count, duplication)
- [ ] GitHub API integration for contributor stats
- [ ] Architecture summary generation via LLM
- [ ] Quality score computation logic
- [ ] Store all results in PostgreSQL

### Phase 4 — Frontend (Week 5–6)

- [ ] Set up Next.js 14 with TypeScript + Tailwind + shadcn/ui
- [ ] Build landing page
- [ ] Build URL input form with SSE progress tracker
- [ ] Build main analysis dashboard (all panels)
- [ ] Build file tree explorer
- [ ] Build AI chat interface with streaming
- [ ] Connect all frontend to backend APIs via TanStack Query
- [ ] Add export functionality (MD/HTML/PDF)
- [ ] Add shareable link generation (signed token + TTL + revoke)
- [ ] Add dependency graph panel (v1.1 if Phase 4 core is stable)

### Phase 5 — Polish & Deploy (Week 7)

- [ ] Write Pytest tests (target >70% coverage)
- [ ] Set up GitHub Actions CI (lint, test, build)
- [ ] Deploy backend to Railway
- [ ] Deploy frontend to Vercel
- [ ] Connect Supabase (PostgreSQL), Qdrant Cloud, Upstash (Redis)
- [ ] Configure custom domain
- [ ] Record YouTube demo walkthrough
- [ ] Write comprehensive README with architecture diagram
- [ ] Run load test for 50k LOC SLA and tune worker concurrency

---

## 11. Non-Functional Requirements

### Performance

- Repo analysis pipeline must complete within 3 minutes for repos ≤ 50k LOC.
- Dashboard page must achieve Lighthouse performance score > 85.
- API endpoints (excluding analysis jobs) must respond within 200ms at p95.
- Chat responses must begin streaming within 1 second of submission.
- Per-stage job timeouts enforced and measured (`clone`, `parse`, `embed`, `analyze`).

### Security

- All API routes (except public share links) require JWT authentication.
- GitHub OAuth tokens stored encrypted at rest.
- Rate limiting: 10 analysis requests/hour for guests, 50/hour for authenticated users.
- Input sanitization on all user-provided repo URLs.
- CORS restricted to frontend domain in production.
- Public share links use signed tokens with default 7-day expiration and optional manual revocation.

### Scalability

- Worker pool designed for horizontal scaling (stateless workers, shared Redis queue).
- Single Qdrant collection with payload filtering by `repo_id`.
- Analysis results cached in Redis for 24 hours to avoid redundant reprocessing.

### Reliability

- Failed jobs automatically retried up to 3 times with exponential backoff.
- Dead-letter queue for permanently failed jobs.
- Health check endpoints for all services (`/health`).
- Analysis submission is idempotent (`Idempotency-Key`) and deduplicated by `repo + commit_sha`.
- Worker stages are resumable from last successful stage.

### Observability

- Track `analysis_duration_seconds` by stage and repo size bucket.
- Track chat retrieval quality metrics (retrieval hit rate, citation presence rate).
- Track p95 endpoint latency and SSE startup latency.

---

## 12. Deployment Plan

### Infrastructure Diagram (Production)

```
Vercel (Next.js)
      │
      │ HTTPS
      ▼
Railway (FastAPI + RQ Workers)
      │
      ├──→ Supabase (PostgreSQL)
      ├──→ Upstash (Redis)
      ├──→ Qdrant Cloud (Vector DB)
      └──→ Cloudflare R2 (File Storage)
```

### Environment Variables

```bash
# Backend
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
QDRANT_URL=https://...
QDRANT_API_KEY=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
OPENROUTER_API_KEY=...
GROQ_API_KEY=...
JWT_SECRET=...
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=7
SHARE_TOKEN_TTL_DAYS=7
R2_BUCKET=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...

# Frontend
NEXT_PUBLIC_API_URL=https://api.devlens.app
APP_URL=https://devlens.app
```

### CI/CD Pipeline (GitHub Actions)

```yaml
# On push to main:
1. Run backend tests (pytest)
2. Run frontend type check (tsc)
3. Run ESLint
4. Build Docker image
5. Push to Docker Hub
6. Deploy to Railway (backend)
7. Deploy to Vercel (frontend)
```

---

## 13. Architecture Decisions (v1.1)

### AD-001: Authentication Authority

- Decision: FastAPI is the single auth authority (GitHub OAuth exchange, JWT issuance, refresh lifecycle).
- Reason: Avoids split-session complexity between frontend and backend auth stacks.
- Consequence: Frontend implements session-aware API client; no separate auth provider issuing tokens.

### AD-002: Vector Storage Isolation

- Decision: Use one shared Qdrant collection with strict `repo_id` payload filters on all queries.
- Reason: Better operational scalability than collection-per-repo on low-cost tiers.
- Consequence: Query validation must reject requests without repo filter.

### AD-003: Hybrid Retrieval

- Decision: Hybrid retrieval = Qdrant dense vectors + PostgreSQL FTS lexical results + cross-encoder rerank.
- Reason: Improves exact symbol/path retrieval while preserving semantic relevance.
- Consequence: `code_chunks` maintains `fts` column and GIN index.

### AD-004: Cache and Reanalysis Strategy

- Decision: Cache keyed by `repo_full_name + default_branch + commit_sha`, TTL 24h.
- Reason: Prevents stale responses when repository head changes.
- Consequence: Analyze endpoint resolves latest default-branch commit before dedupe/cache decision.

### AD-005: Reliability and Idempotency

- Decision: `POST /repos/analyze` requires idempotency support; duplicates return existing active/completed job.
- Reason: Protects system from accidental retries and frontend reconnect loops.
- Consequence: Unique constraints/locks required around active jobs per repo-commit pair.

*Document maintained by Atikul Islam Munna. Update version number and date on each revision.*
