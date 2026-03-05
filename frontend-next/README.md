# DevLens Frontend Next (Parallel Scaffold)

This directory contains the parallel Next.js + TypeScript foundation for migration work.
It does **not** replace the current production frontend yet.

## Routes Included

- `/` home shell
- `/analyze` analyze submission shell
- `/dashboard/[repoId]` dashboard shell

## Environment

Copy `.env.example` to `.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Use your local backend base URL if different.

## Local Run

```bash
npm install
npm run dev
```

Default local port: `3100`.

## Quality Gates

```bash
npm run lint
npm run typecheck
npm run build
```

## Preview Deployment Path

For a parallel preview deployment:

```bash
vercel --cwd frontend-next
```

Set preview env:

- `NEXT_PUBLIC_API_URL=https://<staging-or-preview-backend-domain>`
