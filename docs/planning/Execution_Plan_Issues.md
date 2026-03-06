# DevLens Execution Plan - Ticket-Ready Issues

Use this document to create GitHub issues for the next 2-week execution plan.

Suggested labels:
- `phase:baseline`
- `phase:llm-fallback`
- `phase:reranker`
- `phase:infra-parity`
- `phase:frontend-migration`
- `backend`
- `frontend`
- `workers`
- `infra`
- `qa`

Suggested milestones:
- `M1 Baseline + Reliability`
- `M2 Retrieval Quality`
- `M3 Managed Infra Parity`
- `M4 Frontend Migration Foundation`

---

## Issue 1
**Title:** `M1: Define production baseline metrics and acceptance thresholds`

**Body:**
```md
## Goal
Create a locked baseline for key user flows before introducing new architecture changes.

## Scope
- Define and document target thresholds for:
  - analyze success rate
  - chat citation presence rate
  - first-token chat latency
  - dashboard API p95 latency
- Capture 24h baseline from current production.
- Publish baseline report in `docs/observability/`.

## Deliverables
- Baseline metrics document with thresholds and current values.
- Team sign-off on thresholds.

## Acceptance Criteria
- [ ] Baseline doc exists and is linked in README/docs index.
- [ ] 24h sample window captured.
- [ ] Thresholds are explicit and measurable.
```

**Labels:** `phase:baseline`, `qa`, `infra`

---

## Issue 2
**Title:** `M1: Add end-to-end smoke gate for analyze -> dashboard -> chat`

**Body:**
```md
## Goal
Prevent regressions in the primary user journey while we evolve architecture.

## Scope
- Add smoke checks for:
  - `POST /api/v1/repos/analyze` (job accepted)
  - status progression to terminal state
  - dashboard payload availability
  - chat endpoint streaming starts successfully
- Integrate into CI as a required check or nightly job.

## Acceptance Criteria
- [ ] Smoke script runs locally and in CI.
- [ ] Failures produce actionable output.
- [ ] CI status visible in PR checks.
```

**Labels:** `phase:baseline`, `qa`, `backend`, `workers`

---

## Issue 3
**Title:** `M1: Implement OpenRouter -> Groq fallback chain with provider telemetry`

**Body:**
```md
## Goal
Increase generation reliability by failing over from OpenRouter to Groq when needed.

## Scope
- Add provider router with:
  - primary provider
  - fallback provider
  - timeout and retry policy
- Add env config:
  - `LLM_PRIMARY_PROVIDER`
  - `LLM_FALLBACK_PROVIDER`
  - `GROQ_API_KEY`
  - provider timeouts
- Emit telemetry:
  - provider selected
  - fallback count
  - provider-specific failure codes

## Acceptance Criteria
- [ ] Primary provider failure triggers fallback.
- [ ] Successful fallback returns normal response format.
- [ ] Metrics/logs show fallback event.
- [ ] Existing APIs remain backward-compatible.
```

**Labels:** `phase:llm-fallback`, `backend`, `workers`

---

## Issue 4
**Title:** `M1: Add automated tests for provider fallback behavior`

**Body:**
```md
## Goal
Make fallback behavior deterministic and regression-safe.

## Scope
- Unit tests for provider routing decisions.
- Integration test for simulated OpenRouter failure with Groq success.
- Negative test where both providers fail with clear error envelope.

## Acceptance Criteria
- [ ] Tests pass in CI.
- [ ] Coverage includes timeout, rate-limit, and transport-error branches.
- [ ] Error envelopes remain contract-compliant.
```

**Labels:** `phase:llm-fallback`, `qa`, `backend`

---

## Issue 5
**Title:** `M2: Implement cross-encoder reranker behind feature flag`

**Body:**
```md
## Goal
Improve retrieval relevance before answer synthesis.

## Scope
- Add reranker stage to hybrid retrieval pipeline.
- Add feature flag and config:
  - `RERANK_ENABLED`
  - rerank model id
  - candidate limit
  - rerank timeout
- Add safe fallback to non-reranked results on timeout/error.

## Acceptance Criteria
- [ ] Reranker can be toggled without redeploying code path changes.
- [ ] Timeout/error does not break chat responses.
- [ ] Retrieval output remains schema-compatible.
```

**Labels:** `phase:reranker`, `backend`

---

## Issue 6
**Title:** `M2: Run golden-set evaluation for reranker and publish score delta`

**Body:**
```md
## Goal
Quantify reranker impact before default enablement.

## Scope
- Evaluate baseline vs reranker-on using existing golden dataset.
- Report:
  - relevance delta
  - citation precision/recall
  - latency impact
- Recommendation: default-on or keep flagged.

## Acceptance Criteria
- [ ] Evaluation report committed under `docs/evaluation/`.
- [ ] Decision recorded with thresholds and evidence.
- [ ] If default-on, config docs updated.
```

**Labels:** `phase:reranker`, `qa`, `backend`

---

## Issue 7
**Title:** `M3: Provision staging environment with managed providers parity`

**Body:**
```md
## Goal
Prepare managed-infra parity (Supabase, Upstash, Qdrant Cloud) in staging.

## Scope
- Stand up staging resources:
  - Supabase Postgres
  - Upstash Redis
  - Qdrant Cloud
- Wire staging secrets and service URLs.
- Validate health endpoints and connectivity from backend/worker.

## Acceptance Criteria
- [ ] Staging services reachable and authenticated.
- [ ] Backend and worker boot successfully in staging.
- [ ] Health checks pass for DB/Redis/Qdrant dependencies.
```

**Labels:** `phase:infra-parity`, `infra`

---

## Issue 8
**Title:** `M3: Execute data migration + verification playbook for managed parity`

**Body:**
```md
## Goal
Migrate safely to managed data providers with rollback-ready process.

## Scope
- Schema migration verification.
- Data consistency checks:
  - row counts
  - key table spot checks
  - vector collection integrity
- Document rollback plan and dry-run once.

## Acceptance Criteria
- [ ] Migration checklist completed with evidence.
- [ ] Verification report committed in `docs/release/` or `docs/testing/`.
- [ ] Rollback runbook validated.
```

**Labels:** `phase:infra-parity`, `infra`, `qa`

---

## Issue 9
**Title:** `M3: Canary cutover to managed providers with production monitoring`

**Body:**
```md
## Goal
Switch production dependency endpoints safely with canary rollout.

## Scope
- Enable managed providers for a controlled slice.
- Monitor:
  - error rates
  - latency
  - queue health
  - analysis completion rates
- Complete cutover if metrics stable, otherwise rollback.

## Acceptance Criteria
- [ ] Canary window completed and documented.
- [ ] No critical regression in core flows.
- [ ] Final go/no-go decision recorded.
```

**Labels:** `phase:infra-parity`, `infra`, `backend`, `workers`

---

## Issue 10
**Title:** `M4: Bootstrap Next.js + TypeScript frontend foundation in parallel`

**Body:**
```md
## Goal
Start incremental frontend modernization without disrupting current production UX.

## Scope
- Create parallel Next.js + TypeScript app scaffold.
- Set up routing, shared API client, and base layout.
- Wire env and deployment preview path.

## Acceptance Criteria
- [ ] New frontend scaffold builds and runs.
- [ ] Core lint/type checks enabled.
- [ ] Existing production frontend remains unaffected.
```

**Labels:** `phase:frontend-migration`, `frontend`

---

## Issue 11
**Title:** `M4: Migrate critical routes (/ , /analyze, /dashboard/[repoId]) with API parity`

**Body:**
```md
## Goal
Deliver route-level parity for highest-value screens.

## Scope
- Rebuild:
  - landing
  - analyze (SSE progress)
  - dashboard
- Ensure API contracts, loading/error states, and links match current behavior.

## Acceptance Criteria
- [ ] Route parity validated against current production behavior.
- [ ] Analyze-to-dashboard flow works end-to-end.
- [ ] No regression in auth/session handling.
```

**Labels:** `phase:frontend-migration`, `frontend`, `qa`

---

## Issue 12
**Title:** `M4: Progressive cutover plan and rollback for frontend migration`

**Body:**
```md
## Goal
Ship frontend migration safely via controlled rollout.

## Scope
- Define route-level switch strategy.
- Add observability for frontend errors and latency.
- Provide rollback command/checklist.

## Acceptance Criteria
- [ ] Cutover plan documented and reviewed.
- [ ] Rollback path validated in staging.
- [ ] Production rollout executed without critical incident.
```

**Labels:** `phase:frontend-migration`, `frontend`, `infra`

---

## Dependency Order

1. Issue 1  
2. Issue 2  
3. Issue 3  
4. Issue 4  
5. Issue 5  
6. Issue 6  
7. Issue 7  
8. Issue 8  
9. Issue 9  
10. Issue 10  
11. Issue 11  
12. Issue 12

