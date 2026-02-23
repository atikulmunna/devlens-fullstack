# DEV-071 Golden Repo Relevance Evaluation

This document defines a repeatable manual evaluation process for chat answer relevance and citation correctness.

## 1. Scope

- Ticket: `DEV-071`
- Goal: establish a fixed benchmark set and compare results before/after retrieval or prompt changes.
- Output: scored rows in `docs/evaluation/relevance_scorecard_template.csv`.

## 2. Fixed Evaluation Set

- Dataset file: `docs/evaluation/golden_eval_dataset.json`
- Repository set: 3 public repos across Python, JavaScript/TypeScript, and Go.
- Question set: 9 total prompts (3 per repository).

Rules:
- Keep question text immutable once baseline is recorded.
- If repository list changes, increment dataset `version` and record rationale in PR notes.

## 3. Prerequisites

- Dev stack running (`backend`, `postgres`, `redis`, `qdrant`).
- Each benchmark repository analyzed by DevLens and mapped to a `repo_id`.
- Valid bearer token for an authenticated user.

## 4. Repository Mapping

Create a local mapping file (do not commit secrets or local IDs):

```json
{
  "fastapi": "11111111-1111-1111-1111-111111111111",
  "react": "22222222-2222-2222-2222-222222222222",
  "go": "33333333-3333-3333-3333-333333333333"
}
```

Save as `docs/evaluation/repo_map.local.json` (gitignored if needed).

## 5. Run Collection Command

Use the scripted runner to capture prompt/answer/citation artifacts:

```powershell
./scripts/eval-relevance.ps1 `
  -BaseUrl "http://localhost:8000/api/v1" `
  -AccessToken "<ACCESS_TOKEN>" `
  -DatasetPath "docs/evaluation/golden_eval_dataset.json" `
  -RepoMapPath "docs/evaluation/repo_map.local.json"
```

Script output:
- `artifacts/eval/<run_id>/results.jsonl`

Each JSONL row contains:
- `repo_key`, `repo_id`, `question_id`, `question`
- `answer` (assistant final content)
- `citations`, `no_citation`
- `status` and `error` (if any)

## 6. Scoring Rubric

### 6.1 Answer Relevance (0-3)
- `3`: directly answers request with correct module-level detail.
- `2`: mostly correct but misses one key detail or includes minor drift.
- `1`: partially relevant, high-level, or ambiguous.
- `0`: incorrect or non-responsive.

### 6.2 Citation Correctness (0-3)
- `3`: citations point to clearly relevant files/line ranges supporting claims.
- `2`: mostly correct but one weak/indirect citation.
- `1`: weakly aligned citations or line anchors not clearly supporting answer.
- `0`: incorrect/irrelevant citations, or claims without required support.

### 6.3 Citation Coverage (0-2)
- `2`: all major claims in answer are traceable to citations.
- `1`: some major claims are cited.
- `0`: no meaningful claim-to-citation linkage.

### 6.4 Format and Clarity (0-2)
- `2`: concise, readable, and structured for developer action.
- `1`: understandable but noisy or poorly organized.
- `0`: difficult to interpret.

Total score = `relevance + correctness + coverage + clarity` (0-10).

Pass threshold:
- Per-row pass: `>= 7`
- Run pass: average `>= 7.5` and no row `< 5`

## 7. Baseline vs Post-Change Tracking

For every retrieval/chat change:
1. Run collection and score as `baseline` before change.
2. Run collection and score as `candidate` after change.
3. Compare:
- Average score delta
- Fail count delta
- Citation correctness delta
4. Include comparison summary in PR description.

Suggested summary block:

```text
DEV-071 Eval Summary
- Baseline avg: X.Y
- Candidate avg: X.Y
- Rows < 5: baseline N, candidate N
- Citation correctness avg: baseline X.Y, candidate X.Y
```

## 8. Failure Handling

- If a row has transport or server error, rerun once.
- If still failing, record `status=error` with reason and count as failed row.
- Do not silently drop rows.
