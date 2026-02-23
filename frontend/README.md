# Frontend Service

DevLens frontend app shell (route scaffolding stage).

## Local

1. Copy `.env.example` to `.env.local`.
2. Install dependencies with `npm install`.
3. Start with `npm run dev`.
4. Open `http://localhost:3000`.

## Scaffolded Routes

- `/`
- `/analyze`
- `/dashboard/:repoId`
- `/dashboard/:repoId/chat`
- `/dashboard/:repoId/files`
- `/profile`
- `/share/:token`
- `/health`

## Current Behavior

- `/analyze` submits to `/api/v1/repos/analyze` and opens live SSE status tracking.
- `/dashboard/:repoId` fetches `/api/v1/repos/:repoId/dashboard` and renders overview, quality, architecture, tech debt, contributors, and file tree panels.
- `/dashboard/:repoId` includes export actions: markdown download, HTML download, and print-to-PDF flow.
- `/dashboard/:repoId` includes share-link controls: create/revoke signed public links via `/api/v1/export`.
- `/dashboard/:repoId/chat` supports token-authenticated chat sessions, suggested chips, SSE message streaming, citations, and code block highlighting.
- `/share/:token` resolves public shared analysis payload and renders guarded error states for invalid/expired/revoked tokens.
- `/api/*` is proxied by the frontend service to the backend service.
