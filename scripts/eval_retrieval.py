"""Retrieval quality on a golden set with file-level answers.

Runs inside the backend container against the live index (Postgres, Qdrant, OpenRouter for query
embeddings), the same way chat retrieves (`hybrid_search_chunks`, top 5). Each configuration
changes only how candidates are ranked:

  dense    vector search only
  lexical  Postgres full-text search only
  hybrid   both, fused (production today)
  rerank   hybrid, then the cross-encoder reranker (needs sentence-transformers)

A ":<weight>" suffix sets the test-file weight for that run (hybrid:1.0 ranks tests like any file).

Usage (from the repo root):
  docker compose exec -T backend sh -c 'cat > /tmp/eval_retrieval.py' < scripts/eval_retrieval.py
  docker compose exec -T backend sh -c 'cat > /tmp/golden.json' < docs/evaluation/retrieval_golden.json
  docker compose exec -T -e PYTHONPATH=/app backend python /tmp/eval_retrieval.py /tmp/golden.json hybrid dense lexical
"""

import json
import re
import sys
import time
from contextlib import contextmanager

from sqlalchemy import select

from app.config import settings
from app.db.models import Repository
from app.db.session import SessionLocal
from app.services import reranker, retrieval_hybrid

TOP_K = 5
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$")
PROSE_EXTENSIONS = (".md", ".rst", ".txt")


@contextmanager
def configured(config: str):
    """Temporarily switch retrieval to one configuration."""
    name, _, weight = config.partition(":")
    saved = (
        retrieval_hybrid.lexical_search_chunks,
        retrieval_hybrid.dense_search_qdrant,
        settings.reranker_enabled,
        retrieval_hybrid.TEST_FILE_WEIGHT,
    )
    settings.reranker_enabled = name == "rerank"
    if weight:
        retrieval_hybrid.TEST_FILE_WEIGHT = float(weight)
    if name == "dense":
        retrieval_hybrid.lexical_search_chunks = lambda *_args, **_kwargs: []
    elif name == "lexical":
        retrieval_hybrid.dense_search_qdrant = lambda *_args, **_kwargs: []
    try:
        yield
    finally:
        (
            retrieval_hybrid.lexical_search_chunks,
            retrieval_hybrid.dense_search_qdrant,
            settings.reranker_enabled,
            retrieval_hybrid.TEST_FILE_WEIGHT,
        ) = saved


def score_question(paths: list[str], relevant: set[str]) -> dict:
    first_hit = next((rank for rank, path in enumerate(paths, start=1) if path in relevant), None)
    return {
        "hit": first_hit is not None,
        "reciprocal_rank": 1 / first_hit if first_hit else 0.0,
        "file_recall": len(relevant & set(paths)) / len(relevant),
        "test_share": sum(bool(TEST_PATH.search(p)) for p in paths) / max(len(paths), 1),
        "prose_share": sum(p.lower().endswith(PROSE_EXTENSIONS) for p in paths) / max(len(paths), 1),
    }


def run(golden: dict, name: str) -> dict:
    rows = []
    with SessionLocal() as db, configured(name):
        for repo in golden["repos"]:
            repo_id = db.execute(select(Repository.id).where(Repository.full_name == repo["full_name"])).scalar_one()
            for item in repo["questions"]:
                started = time.perf_counter()
                results = retrieval_hybrid.hybrid_search_chunks(db, repo_id=repo_id, query=item["question"], limit=TOP_K)
                latency_ms = (time.perf_counter() - started) * 1000
                paths = [str(r.get("file_path") or "") for r in results]
                rows.append({"id": item["id"], "latency_ms": latency_ms, "top": paths, **score_question(paths, set(item["relevant_files"]))})
    count = len(rows)
    return {
        "config": name,
        "recall_at_5": sum(r["hit"] for r in rows) / count,
        "mrr_at_5": sum(r["reciprocal_rank"] for r in rows) / count,
        "file_recall_at_5": sum(r["file_recall"] for r in rows) / count,
        "test_share": sum(r["test_share"] for r in rows) / count,
        "prose_share": sum(r["prose_share"] for r in rows) / count,
        "latency_ms_avg": sum(r["latency_ms"] for r in rows) / count,
        "misses": [r["id"] for r in rows if not r["hit"]],
        "rows": rows,
    }


def main() -> None:
    golden = json.load(open(sys.argv[1], encoding="utf-8"))
    configs = sys.argv[2:] or ["dense", "lexical", "hybrid", "rerank"]
    if any(config.startswith("rerank") for config in configs):
        try:
            reranker._load_cross_encoder(settings.reranker_model)  # load once, outside the timings
        except reranker.RerankerUnavailable as exc:
            print(f"skipping rerank: {exc}", file=sys.stderr)
            configs = [config for config in configs if not config.startswith("rerank")]
    reports = [run(golden, name) for name in configs]
    print(json.dumps(reports))


if __name__ == "__main__":
    main()
