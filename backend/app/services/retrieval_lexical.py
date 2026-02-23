from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session


def lexical_search_chunks(db: Session, repo_id: UUID, query: str, limit: int = 20) -> list[dict]:
    q = query.strip()
    if not q:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query must not be empty")

    safe_limit = max(1, min(limit, 100))
    rows = db.execute(
        text(
            """
            SELECT id::text AS chunk_id,
                   file_path,
                   start_line,
                   end_line,
                   language,
                   ts_rank_cd(fts, plainto_tsquery('english', :query)) AS score
            FROM code_chunks
            WHERE repo_id = CAST(:repo_id AS uuid)
              AND fts @@ plainto_tsquery('english', :query)
            ORDER BY score DESC, file_path ASC, start_line ASC NULLS LAST
            LIMIT :limit
            """
        ),
        {"repo_id": str(repo_id), "query": q, "limit": safe_limit},
    ).mappings().all()

    return [
        {
            "chunk_id": row["chunk_id"],
            "file_path": row["file_path"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "language": row["language"],
            "score": float(row["score"] or 0.0),
        }
        for row in rows
    ]
