# DEV-045 Reranker Golden-Set Evaluation Report

Generated: 2026-03-05 01:33:00 +06:00

## Inputs
- Baseline results: artifacts/eval/20260305-012818/results.jsonl
- Candidate results: artifacts/eval/20260305-012931/results.jsonl
- Baseline scorecard: docs/evaluation/scorecard_baseline.csv
- Candidate scorecard: docs/evaluation/scorecard_candidate.csv

## Metrics
| Metric | Baseline | Candidate (reranker-on) | Delta (cand - base) |
|---|---:|---:|---:|
| Relevance avg (0-3) | 0.556 | 0.556 | 0 |
| Citation correctness avg (0-3) | 0.444 | 0.444 | 0 |
| Citation precision (proxy) | 0 | 0 | 0 |
| Citation recall (proxy) | 0 | 0 | 0 |
| Total avg (0-10) | 2.444 | 2.444 | 0 |
| Avg latency (ms) | 74.98 | 80.028 | 5.048 |

## Sample Sizes
- Baseline scored rows: 9
- Candidate scored rows: 9
- Baseline latency rows: 9
- Candidate latency rows: 9

## Recommendation
- Decision: keep reranker behind feature flag (do not default-on).
- Rationale:
  - No measured quality gain on this run (`total`, `relevance`, `citation correctness` deltas are all `0`).
  - Candidate adds latency (+`5.048` ms average) without retrieval quality improvement.
  - Go benchmark queries returned no relevant context in both runs; indexing/retrieval quality should be improved before re-evaluating default enablement.
- Next actions:
  - Improve chunk coverage/selection for large repos and re-run DEV-045 with refreshed scorecards.
  - Re-evaluate default-on only after positive quality delta at acceptable latency cost.
