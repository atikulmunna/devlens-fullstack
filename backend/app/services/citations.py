from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def format_citation(
    *,
    chunk_id: str,
    file_path: str,
    line_start: int | None,
    line_end: int | None,
    score: float | None = None,
) -> dict:
    start = int(line_start or 1)
    end = int(line_end or start)
    if end < start:
        end = start
    anchor = f"{file_path}#L{start}-L{end}"
    return {
        "chunk_id": chunk_id,
        "file_path": file_path,
        "line_start": start,
        "line_end": end,
        "anchor": anchor,
        "score": float(score or 0.0),
    }


def validate_citations_for_repo(db: Session, repo_id: UUID, citations: list[dict]) -> list[dict]:
    valid: list[dict] = []
    for citation in citations:
        chunk_id = citation.get("chunk_id")
        file_path = citation.get("file_path")
        line_start = citation.get("line_start")
        line_end = citation.get("line_end")

        if not chunk_id or not file_path:
            continue

        row = db.execute(
            text(
                """
                SELECT file_path, start_line, end_line
                FROM code_chunks
                WHERE id = CAST(:chunk_id AS uuid)
                  AND repo_id = CAST(:repo_id AS uuid)
                LIMIT 1
                """
            ),
            {"chunk_id": chunk_id, "repo_id": str(repo_id)},
        ).mappings().first()
        if not row:
            continue

        if row["file_path"] != file_path:
            continue

        db_start = int(row["start_line"] or 1)
        db_end = int(row["end_line"] or db_start)
        c_start = int(line_start or db_start)
        c_end = int(line_end or c_start)
        if c_start < db_start or c_end > db_end:
            continue

        valid.append(
            {
                **citation,
                "line_start": c_start,
                "line_end": c_end,
                "anchor": f"{file_path}#L{c_start}-L{c_end}",
            }
        )

    return valid
