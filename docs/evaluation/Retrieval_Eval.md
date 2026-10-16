# Retrieval Quality Evaluation

Status: **measured 2026-10-15** on the live local index. Decision: keep the cross-encoder reranker
off; rank test files lower unless the question is about tests.

## What is measured

Chat answers are only as good as the chunks retrieval hands the model. This eval asks: for a real
question, does a chunk from a file that actually answers it reach the top 5 (what chat retrieves)?

- Golden set: `docs/evaluation/retrieval_golden.json`, 25 questions on two indexed repos
  (11 on `pallets/itsdangerous`, 14 on `atikulmunna/devlens-fullstack` as of main `c1cf51b`).
  Each question lists the implementation files that answer it, checked against the indexed code.
  Questions do not name files, so path matching alone cannot answer them.
- Metrics, all over the top 5 chunks:
  - **Recall@5**: share of questions with at least one chunk from an answering file.
  - **MRR@5**: mean of 1 / rank of the first answering chunk (0 when none).
  - **File recall@5**: share of each question's answering files that appear.
  - **Test share / prose share**: share of the top 5 that are test files / md, rst, txt.
  - **Latency**: wall time of `hybrid_search_chunks`, including the OpenRouter query embedding.
- Index: OpenRouter `openai/text-embedding-3-small` (1536 dims) in Qdrant, Postgres full-text
  search, tree-sitter chunks of up to 120 lines.

## Results

| Ranking | Recall@5 | MRR@5 | File recall@5 | Test share | Prose share | Latency |
|---|---:|---:|---:|---:|---:|---:|
| Lexical only | 0.36 | 0.36 | 0.29 | 0.05 | 0.15 | 1 ms |
| Dense only | 0.84 | 0.71 | 0.73 | 0.27 | 0.10 | 1658 ms |
| Hybrid (before) | 0.84 | 0.75 | 0.77 | 0.26 | 0.10 | 1551 ms |
| **Hybrid, tests at 0.6 (shipped)** | **0.88** | **0.80** | **0.79** | **0.04** | 0.18 | 1515 ms |
| Hybrid + reranker | 0.88 | 0.83 | 0.75 | 0.25 | 0.15 | 2560 ms |
| Hybrid, tests at 0.6, + reranker | 0.88 | 0.83 | 0.75 | 0.25 | 0.15 | 2561 ms |

Per repo (questions found): itsdangerous 10/11 in every configuration except lexical (4/11);
DevLens 11/14 before, 12/14 with the test weight or the reranker, 5/14 lexical.

Test-file weight sweep (hybrid): 1.0 gives 0.84 / 0.75 (Recall / MRR), 0.8 gives 0.84 / 0.79,
0.6 gives 0.88 / 0.80, 0.4 gives 0.88 / 0.80. 0.6 is the mildest weight with the full gain.

Latency is measured on a desktop CPU; nearly all of it is the query embedding round trip.

## Findings

1. **Dense retrieval carries the ranking.** Full-text search matches natural-language questions
   poorly (0.36); fusion adds little over dense alone except on MRR.
2. **Test files crowded out the implementation.** A quarter of the top 5 were tests, which restate
   the code they exercise. For "what does the chat endpoint do when the model call fails?", three of
   the five were `test_chat.py` chunks. Scaling the fused score of test files by 0.6, unless the
   question mentions tests, raised Recall@5 from 0.84 to 0.88 and MRR from 0.75 to 0.80 at no cost.
3. **The reranker does not pay for itself.** Over the shipped ranking it finds no more questions,
   lifts MRR by 0.03, lowers file recall (0.79 to 0.75), and brings test files back to a quarter of
   the results (it re-sorts by its own score, after the test weight). It adds about a second per
   query on a desktop CPU, more on the small production instance, and the backend image grows from
   329 MB to 3.27 GB (torch).

## Decision

- `reranker_enabled` defaults to `False` (production already forced it off). The reranker code and
  the `INSTALL_RERANKER` build flag stay, so it can be re-measured with the script below.
- Ship the test-file weight: `SUPPORTING_FILE_WEIGHT = 0.6` in `backend/app/services/retrieval_hybrid.py`.
  (2026-10-16: CI and tooling files such as `.github/workflows/*` now share it, after a production
  "main architecture components" question retrieved only workflow files.)

## Remaining misses (hybrid, tests at 0.6)

- ITS-6 "When is the payload compressed before signing?": changelog entries outrank `url_safe.py`
  (prose share rose to 0.18 once tests dropped; a similar weight for prose is the next thing to try).
- DL-3 "What does the chat endpoint do when the model call fails?": the fallback lives deep in a
  long `chat.py`, which never enters the candidate pool.
- DL-9 "How are the files impacted by a commit found?": `diff.py`, which calls the blast radius,
  ranks; `blast_radius.py` itself does not.

## How to run

With the local stack up and both repos analyzed:

```sh
docker compose exec -T backend sh -c 'cat > /tmp/eval_retrieval.py' < scripts/eval_retrieval.py
docker compose exec -T backend sh -c 'cat > /tmp/golden.json' < docs/evaluation/retrieval_golden.json
docker compose exec -T -e PYTHONPATH=/app backend python /tmp/eval_retrieval.py /tmp/golden.json dense lexical hybrid hybrid:1.0
```

Configurations: `dense`, `lexical`, `hybrid`, `rerank`; a `:<weight>` suffix sets the test-file
weight for that run. The script prints one JSON report per configuration, with per-question top 5.

The reranker needs an image with it installed. Build one separately and mount the current code:

```sh
docker build --build-arg INSTALL_RERANKER=true -t devlens-backend-rerank:eval ./backend
docker run --rm --network devlens_default --env-file backend/.env.example --env-file backend/.env \
  -e PYTHONPATH=/app -v "$PWD/backend/app:/app/app:ro" -v "$PWD/scripts:/eval/scripts:ro" \
  -v "$PWD/docs/evaluation:/eval/docs:ro" devlens-backend-rerank:eval \
  python /eval/scripts/eval_retrieval.py /eval/docs/retrieval_golden.json hybrid rerank
```

Repos are matched by `full_name`, so re-analyzing a repo changes its chunks but not the golden set.
When a golden repo's code changes, re-check its `relevant_files`.

## History

The earlier plan in this file (NIM `nv-embedqa-e5-v5` embedder, hash-embedder baseline) never ran;
the NIM model was retired and embeddings moved to OpenRouter before it could. The older reranker
report (`DEV-045_Reranker_Delta_Report.md`) measured no delta with the hash embedder.
