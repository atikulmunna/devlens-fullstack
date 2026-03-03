# DEV-045 Reranker Golden-Set Evaluation Report

Status: pending baseline/candidate run inputs.

## Goal

Compare baseline retrieval vs reranker-enabled retrieval on the fixed golden dataset and publish score deltas.

## Required Inputs

- `artifacts/eval/<baseline_run>/results.jsonl`
- `artifacts/eval/<candidate_run>/results.jsonl`
- `docs/evaluation/scorecard_baseline.csv` (manual-scored)
- `docs/evaluation/scorecard_candidate.csv` (manual-scored)

## Commands

1. Collect baseline:

```powershell
./scripts/eval-relevance.ps1 `
  -BaseUrl "http://localhost:8000/api/v1" `
  -AccessToken "<ACCESS_TOKEN>" `
  -RunType "baseline" `
  -DatasetPath "docs/evaluation/golden_eval_dataset.json" `
  -RepoMapPath "docs/evaluation/repo_map.local.json"
```

2. Collect candidate (reranker on):

```powershell
./scripts/eval-relevance.ps1 `
  -BaseUrl "http://localhost:8000/api/v1" `
  -AccessToken "<ACCESS_TOKEN>" `
  -RunType "candidate" `
  -DatasetPath "docs/evaluation/golden_eval_dataset.json" `
  -RepoMapPath "docs/evaluation/repo_map.local.json"
```

3. Compute delta report:

```powershell
./scripts/eval-reranker-delta.ps1 `
  -BaselineResultsPath "artifacts/eval/<baseline_run>/results.jsonl" `
  -CandidateResultsPath "artifacts/eval/<candidate_run>/results.jsonl" `
  -BaselineScorecardPath "docs/evaluation/scorecard_baseline.csv" `
  -CandidateScorecardPath "docs/evaluation/scorecard_candidate.csv" `
  -OutputPath "docs/evaluation/DEV-045_Reranker_Delta_Report.md"
```

## Decision

- [ ] Default reranker ON
- [ ] Keep reranker behind flag

Decision notes:
- Pending
