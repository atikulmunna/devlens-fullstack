import hashlib
import logging
import math
import re
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.reranker import RerankerUnavailable, rerank_candidates
from app.services.retrieval_lexical import lexical_search_chunks

logger = logging.getLogger(__name__)


def _embed_query(query: str, size: int = 384) -> list[float]:
    # Deterministic local embedder used until model-backed embedder is integrated.
    digest = hashlib.sha256(query.encode("utf-8")).digest()
    seed = list(digest) * ((size // len(digest)) + 1)
    vector = [(b / 255.0) * 2.0 - 1.0 for b in seed[:size]]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def dense_search_qdrant(repo_id: str, query: str, limit: int) -> list[dict]:
    if not repo_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo_id filter is required")

    vector = _embed_query(query)
    url = f"{str(settings.qdrant_url).rstrip('/')}/collections/{settings.qdrant_collection}/points/search"
    body = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "filter": {"must": [{"key": "repo_id", "match": {"value": repo_id}}]},
    }
    headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else None

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=body, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Qdrant request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Qdrant search failed")

    payload = response.json()
    points = payload.get("result", [])
    results: list[dict] = []
    for point in points:
        point_payload = point.get("payload", {}) or {}
        chunk_id = point_payload.get("chunk_id")
        if not chunk_id:
            continue
        results.append(
            {
                "chunk_id": str(chunk_id),
                "file_path": point_payload.get("file_path"),
                "start_line": point_payload.get("start_line"),
                "end_line": point_payload.get("end_line"),
                "language": point_payload.get("language"),
                "dense_score": float(point.get("score") or 0.0),
            }
        )
    return results


def _normalize_scores(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    min_v = min(values.values())
    max_v = max(values.values())
    if max_v == min_v:
        return {k: 1.0 for k in values}
    return {k: (v - min_v) / (max_v - min_v) for k, v in values.items()}


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if token}


def _load_chunk_content(db: Session, repo_id: UUID, chunk_ids: list[str]) -> dict[str, str]:
    if not chunk_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT id::text AS chunk_id, content
            FROM code_chunks
            WHERE repo_id = CAST(:repo_id AS uuid)
              AND id = ANY(CAST(:chunk_ids AS uuid[]))
            """
        ),
        {"repo_id": str(repo_id), "chunk_ids": chunk_ids},
    ).mappings().all()
    return {row["chunk_id"]: row.get("content") or "" for row in rows}


def _apply_cross_encoder_rerank(db: Session, repo_id: UUID, query: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    candidate_limit = max(1, min(settings.reranker_candidate_limit, len(rows)))
    candidates = rows[:candidate_limit]
    chunk_ids = [row["chunk_id"] for row in candidates]
    contents = _load_chunk_content(db, repo_id=repo_id, chunk_ids=chunk_ids)
    rerank_input = [
        {
            "chunk_id": row["chunk_id"],
            "file_path": row.get("file_path"),
            "language": row.get("language"),
            "content": contents.get(row["chunk_id"], ""),
        }
        for row in candidates
    ]
    try:
        score_map = rerank_candidates(query=query, candidates=rerank_input, model_name=settings.reranker_model)
    except RerankerUnavailable as exc:
        logger.warning("Cross-encoder reranker unavailable; using deterministic ranking: %s", exc)
        return rows
    except Exception as exc:
        logger.warning("Cross-encoder reranker failed; using deterministic ranking: %s", exc)
        return rows
    if not score_map:
        return rows
    for row in rows:
        if row["chunk_id"] in score_map:
            row["rerank_score"] = round(score_map[row["chunk_id"]], 6)
    return sorted(rows, key=lambda row: (-row["rerank_score"], row["chunk_id"]))


def hybrid_search_chunks(db: Session, repo_id: UUID, query: str, limit: int = 20) -> list[dict]:
    q = query.strip()
    if not q:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query must not be empty")
    safe_limit = max(1, min(limit, 100))

    lexical = lexical_search_chunks(db, repo_id=repo_id, query=q, limit=safe_limit * 2)
    dense = dense_search_qdrant(str(repo_id), q, safe_limit * 2)

    merged: dict[str, dict] = {}
    for item in lexical:
        merged[item["chunk_id"]] = {
            **item,
            "dense_score": 0.0,
            "lexical_score": float(item["score"]),
        }
    for item in dense:
        existing = merged.get(item["chunk_id"], {})
        merged[item["chunk_id"]] = {
            "chunk_id": item["chunk_id"],
            "file_path": existing.get("file_path") or item.get("file_path"),
            "start_line": existing.get("start_line") if existing else item.get("start_line"),
            "end_line": existing.get("end_line") if existing else item.get("end_line"),
            "language": existing.get("language") or item.get("language"),
            "dense_score": float(item["dense_score"]),
            "lexical_score": float(existing.get("lexical_score") or 0.0),
            "score": float(existing.get("score") or 0.0),
        }

    dense_norm = _normalize_scores({cid: row.get("dense_score", 0.0) for cid, row in merged.items()})
    lexical_norm = _normalize_scores({cid: row.get("lexical_score", 0.0) for cid, row in merged.items()})

    query_terms = _tokenize(q)
    for chunk_id, row in merged.items():
        file_terms = _tokenize(f"{row.get('file_path') or ''} {row.get('language') or ''}")
        overlap = 0.0
        if query_terms and file_terms:
            overlap = len(query_terms.intersection(file_terms)) / len(query_terms)
        row["rerank_score"] = round(
            0.45 * dense_norm.get(chunk_id, 0.0)
            + 0.35 * lexical_norm.get(chunk_id, 0.0)
            + 0.20 * overlap,
            6,
        )

    ranked = sorted(merged.values(), key=lambda row: (-row["rerank_score"], row["chunk_id"]))
    if settings.reranker_enabled:
        ranked = _apply_cross_encoder_rerank(db, repo_id=repo_id, query=q, rows=ranked)
    return ranked[:safe_limit]
