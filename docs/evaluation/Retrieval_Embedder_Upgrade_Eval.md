# Retrieval Embedder Upgrade: Evaluation Plan and Delta Report

Status: **results pending live re-run** (see "How to run" below). This document records the change,
its rationale, and the exact procedure to populate the metrics table from a real evaluation.

## Change under evaluation

1. **Real embeddings (Task 1).** The dense retrieval path previously used a SHA-256 hash as a stand-in
   "embedder" on both the index side (`workers/embeddings.py`) and query side
   (`backend/app/services/retrieval_hybrid.py`). Both are replaced with NVIDIA NIM model embeddings
   (`nvidia/nv-embedqa-e5-v5`, 1024-dim, asymmetric `query`/`passage` input types) sharing one vector space.
2. **Code-aware chunking (Task 2).** `workers/chunking.py` splits source at tree-sitter definition
   boundaries instead of fixed line windows; the file-type allow-list was widened to config/IaC/SQL/docs.
3. **Fusion + reranker (Task 3).** Hybrid fusion weights rebalanced to `0.50 dense / 0.40 lexical /
   0.10 path-overlap`; the cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) is enabled by
   default (`reranker_enabled: True`) and `sentence-transformers` added to backend requirements.

## Why re-evaluate now

The prior reranker evaluation (`DEV-045_Reranker_Delta_Report.md`) measured **zero** quality delta and
recommended keeping the reranker behind a flag. Its own diagnosis was that retrieval quality was the
blocker: "Go benchmark queries returned no relevant context in both runs; indexing/retrieval quality
should be improved before re-evaluating default enablement." That blocker was the hash embedder, which is
now removed. Enabling the reranker by default is therefore provisional and must be confirmed by the re-run
below; if the delta is not positive at acceptable latency, revert `reranker_enabled` to `False`.

## Metrics (to be filled from a live run)

| Metric | Baseline (hash embedder) | Candidate (NIM + tree-sitter + reranker) | Delta |
|---|---:|---:|---:|
| Recall@5 | _pending_ | _pending_ | _pending_ |
| Relevance avg (0-3) | _pending_ | _pending_ | _pending_ |
| Citation correctness avg (0-3) | _pending_ | _pending_ | _pending_ |
| Total avg (0-10) | _pending_ | _pending_ | _pending_ |
| Avg latency (ms) | _pending_ | _pending_ | _pending_ |

## How to run (live environment with NIM key + full stack)

1. Bring up the stack: `scripts/dev-up.ps1` (Postgres, Redis, Qdrant, backend, worker).
2. Set `NIM_API_KEY` (backend + worker env). Analyze the golden repos so vectors repopulate at 1024-dim
   (the worker auto-recreates the Qdrant collection on first embed).
3. Baseline capture: check out the pre-change commit (or set `reranker_enabled=False` and the hash
   embedder) and run `scripts/eval-relevance.ps1` to produce `results.jsonl` + scorecard.
4. Candidate capture: on this change, run `scripts/eval-relevance.ps1` again.
5. Delta: `scripts/eval-reranker-delta.ps1 -BaselineResultsPath ... -CandidateResultsPath ...
   -BaselineScorecardPath ... -CandidateScorecardPath ...` and paste the emitted table above.
6. Chat quality: `scripts/eval-chat-quality.ps1` against `docs/evaluation/chat_quality_dataset.sample.json`.

## Decision gate

- Ship default-on reranker only if the candidate shows a positive relevance/recall delta at acceptable
  added latency; otherwise set `reranker_enabled=False` and keep dense+lexical fusion.
