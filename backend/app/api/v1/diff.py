import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.db.models import CommitDiff, Repository, User
from app.deps import get_current_user, get_db_session
from app.services.blast_radius import compute_blast_radius
from app.services.chat_synthesizer import ChatSynthesisError, synthesize_grounded_answer_stream

router = APIRouter(prefix="/repos", tags=["diff"])


class DiffAskRequest(BaseModel):
    question: str


def _latest_diff(db: Session, repo_id: UUID, head: str | None) -> CommitDiff | None:
    query = select(CommitDiff).where(CommitDiff.repo_id == repo_id)
    if head:
        query = query.where(CommitDiff.head_sha == head)
    query = query.order_by(CommitDiff.created_at.desc())
    return db.execute(query).scalars().first()


def _load_file_chunks(db: Session, repo_id: UUID) -> list[dict]:
    rows = db.execute(
        text("SELECT file_path, content FROM code_chunks WHERE repo_id = CAST(:repo_id AS uuid)"),
        {"repo_id": str(repo_id)},
    ).mappings().all()
    return [{"file_path": row["file_path"], "content": row["content"]} for row in rows]


def _summarize_changed(changed_files: list[dict]) -> list[dict]:
    summary = []
    for entry in changed_files:
        summary.append(
            {
                "path": entry.get("path"),
                "status": entry.get("status"),
                "added": entry.get("added", 0),
                "removed": entry.get("removed", 0),
                "hunks": len(entry.get("hunks") or []),
            }
        )
    return summary


def _diff_intent(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["security", "auth", "secret", "token", "vulnerab", "risk", "credential", "password"]):
        return "security"
    if any(w in q for w in ["architecture", "design", "structure", "coupling"]):
        return "architecture"
    if any(w in q for w in ["break", "broke", "fail", "bug", "regress", "impact", "affect", "caller"]):
        return "debug"
    return "general"


def _diff_contexts(changed_files: list[dict], limit: int = 6) -> list[dict]:
    contexts = []
    for entry in changed_files[:limit]:
        hunks = entry.get("hunks") or []
        added = entry.get("added_lines") or []
        contexts.append(
            {
                "chunk_id": entry.get("path"),
                "file_path": entry.get("path"),
                "line_start": hunks[0]["start"] if hunks else None,
                "line_end": hunks[-1]["end"] if hunks else None,
                "language": None,
                "content": "\n".join(added[:60]),
            }
        )
    return contexts


@router.get(
    "/{repo_id}/diff",
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def get_commit_diff(
    repo_id: UUID,
    head: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    diff = _latest_diff(db, repo_id, head)
    if not diff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No commit diff available for this repository")

    changed_files = diff.changed_files or []
    changed_paths = [entry.get("path") for entry in changed_files if entry.get("path")]
    blast = compute_blast_radius(_load_file_chunks(db, repo_id), changed_paths)

    return {
        "repo_id": str(repo_id),
        "base_sha": diff.base_sha,
        "head_sha": diff.head_sha,
        "changed_files": _summarize_changed(changed_files),
        "security_flags": diff.security_flags or [],
        "blast_radius": blast,
        "created_at": diff.created_at.isoformat() if diff.created_at else None,
    }


@router.post(
    "/{repo_id}/diff/ask",
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def ask_about_diff(
    repo_id: UUID,
    payload: DiffAskRequest,
    head: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if not payload.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question must not be empty")

    diff = _latest_diff(db, repo_id, head)
    if not diff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No commit diff available for this repository")

    changed_files = diff.changed_files or []
    contexts = _diff_contexts(changed_files)
    intent = _diff_intent(payload.question)
    security_categories = sorted(
        {cat for flag in (diff.security_flags or []) for cat in (flag.get("categories") or [])}
    )

    def _delta(token: str) -> str:
        return f"event: delta\ndata: {json.dumps({'token': token})}\n\n"

    def _fallback_text() -> str:
        summary = _summarize_changed(changed_files)
        touched = ", ".join(item["path"] for item in summary[:8]) or "no files"
        note = f" Security-sensitive areas: {', '.join(security_categories)}." if security_categories else ""
        return f"This commit ({diff.head_sha[:10]}) changed: {touched}.{note}"

    async def event_stream():
        parts: list[str] = []
        try:
            for piece in synthesize_grounded_answer_stream(
                query=payload.question,
                contexts=contexts,
                intent=intent,
            ):
                parts.append(piece)
                yield _delta(piece)
                await asyncio.sleep(0)
        except ChatSynthesisError:
            pass

        if not "".join(parts).strip():
            for token in _fallback_text().split(" "):
                yield _delta(token + " ")
                await asyncio.sleep(0)

        final = {
            "head_sha": diff.head_sha,
            "base_sha": diff.base_sha,
            "security_categories": security_categories,
        }
        yield f"event: done\ndata: {json.dumps(final)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
