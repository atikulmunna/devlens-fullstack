import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.api.sse import SSE_HEADERS, sse_event, stream_answer
from app.db.models import CommitDiff, User
from app.deps import get_current_user, get_db_session, get_repo_or_404
from app.services.blast_radius import compute_blast_radius
from app.services.chat_synthesizer import detect_intent, synthesize_grounded_answer_stream

router = APIRouter(prefix="/repos", tags=["diff"])


class DiffAskRequest(BaseModel):
    question: str


class HunkLineResponse(BaseModel):
    # "+" added, "-" removed, " " unchanged context.
    kind: Literal["+", "-", " "]
    text: str
    old: int | None = None
    new: int | None = None
    # Security patterns this line matches, e.g. ["token"].
    labels: list[str] = []


class HunkResponse(BaseModel):
    start: int
    end: int
    old_start: int | None = None
    lines: list[HunkLineResponse] = []


class ChangedFileResponse(BaseModel):
    path: str
    status: str
    added: int
    removed: int
    hunks: int
    # Line detail for the diff viewer; empty for diffs stored before it was captured.
    hunk_details: list[HunkResponse] = []
    # True when some lines were left out to keep the stored diff bounded.
    truncated: bool = False


class SecurityFlagResponse(BaseModel):
    path: str
    # e.g. "auth", "token", or "removed: token" for a match in removed lines.
    categories: list[str]
    severity: Literal["high", "medium", "low"]


class BlastRadiusResponse(BaseModel):
    changed_files: list[str]
    impacted_files: list[str]
    impacted_count: int
    # impacted_by_depth[0] imports a changed file directly, [1] imports one of those, and so on.
    impacted_by_depth: list[list[str]] = []
    graph_stats: dict[str, int]


class CommitDiffEntry(BaseModel):
    head_sha: str
    base_sha: str | None
    created_at: datetime | None
    changed_count: int


class CommitDiffListResponse(BaseModel):
    repo_id: str
    diffs: list[CommitDiffEntry]


# Secrets and keys are exposed the moment they land; removing an auth or token check is as serious.
HIGH_RISK = {"secret", "credential", "password", "api_key"}
MEDIUM_RISK = {"auth", "token", "jwt", "oauth", "crypto"}


def _flag_severity(categories: list[str]) -> str:
    plain = {category.removeprefix("removed: ") for category in categories}
    removed = {category.removeprefix("removed: ") for category in categories if category.startswith("removed: ")}
    if plain & HIGH_RISK or removed & MEDIUM_RISK:
        return "high"
    if plain & MEDIUM_RISK:
        return "medium"
    return "low"


def _with_severity(flags: list[dict]) -> list[dict]:
    return [{**flag, "severity": _flag_severity(flag.get("categories") or [])} for flag in flags]


class CommitDiffResponse(BaseModel):
    repo_id: str
    base_sha: str | None
    head_sha: str
    changed_files: list[ChangedFileResponse]
    security_flags: list[SecurityFlagResponse]
    blast_radius: BlastRadiusResponse
    created_at: datetime | None


def _latest_diff(db: Session, repo_id: UUID, head: str | None) -> CommitDiff | None:
    query = select(CommitDiff).where(CommitDiff.repo_id == repo_id)
    if head:
        query = query.where(CommitDiff.head_sha == head)
    query = query.order_by(CommitDiff.created_at.desc())
    return db.execute(query).scalars().first()


def _load_file_chunks(db: Session, repo_id: UUID) -> list[dict]:
    rows = (
        db.execute(
            text("SELECT file_path, content FROM code_chunks WHERE repo_id = CAST(:repo_id AS uuid)"),
            {"repo_id": str(repo_id)},
        )
        .mappings()
        .all()
    )
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
                "hunk_details": [hunk for hunk in entry.get("hunks") or [] if hunk.get("lines")],
                "truncated": bool(entry.get("truncated")),
            }
        )
    return summary


def _rank_for_question(changed_files: list[dict], question: str) -> list[dict]:
    """Files whose path names words from the question first ("embed worker" finds embed_worker.py);
    otherwise diff order. Only the first few files fit in the model's context."""
    words = {word for word in re.findall(r"[a-z0-9]+", question.lower()) if len(word) >= 3}

    def matches(entry: dict) -> int:
        return len(words & set(re.findall(r"[a-z0-9]+", str(entry.get("path") or "").lower())))

    return sorted(changed_files, key=matches, reverse=True)


def _diff_contexts(changed_files: list[dict], limit: int = 6, lines_per_side: int = 60) -> list[dict]:
    """One context per changed file, in diff notation: "+" for added lines, "-" for removed ones.

    Diffs stored before removed lines were captured simply have no "-" lines.
    """
    contexts = []
    for entry in changed_files[:limit]:
        hunks = entry.get("hunks") or []
        added = [f"+{line}" for line in (entry.get("added_lines") or [])[:lines_per_side]]
        removed = [f"-{line}" for line in (entry.get("removed_lines") or [])[:lines_per_side]]
        contexts.append(
            {
                "chunk_id": entry.get("path"),
                "file_path": entry.get("path"),
                "line_start": hunks[0]["start"] if hunks else None,
                "line_end": hunks[-1]["end"] if hunks else None,
                "language": None,
                "content": "\n".join(removed + added),
            }
        )
    return contexts


@router.get(
    "/{repo_id}/diffs",
    response_model=CommitDiffListResponse,
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def list_commit_diffs(
    repo_id: UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> CommitDiffListResponse:
    """The analyzed commits with a stored diff, newest first: what the commit picker offers."""
    get_repo_or_404(db, repo_id)
    rows = db.execute(
        select(
            CommitDiff.head_sha,
            CommitDiff.base_sha,
            CommitDiff.created_at,
            func.coalesce(func.jsonb_array_length(CommitDiff.changed_files), 0),
        )
        .where(CommitDiff.repo_id == repo_id)
        .distinct(CommitDiff.head_sha)
        .order_by(CommitDiff.head_sha, CommitDiff.created_at.desc())
    ).all()
    entries = [
        CommitDiffEntry(head_sha=head, base_sha=base, created_at=created, changed_count=count)
        for head, base, created, count in rows
    ]
    entries.sort(key=lambda entry: entry.created_at or datetime.min, reverse=True)
    return CommitDiffListResponse(repo_id=str(repo_id), diffs=entries[:20])


@router.get(
    "/{repo_id}/diff",
    response_model=CommitDiffResponse,
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
    get_repo_or_404(db, repo_id)

    diff = _latest_diff(db, repo_id, head)
    if not diff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No commit diff available for this repository"
        )

    changed_files = diff.changed_files or []
    changed_paths = [entry.get("path") for entry in changed_files if entry.get("path")]
    blast = compute_blast_radius(_load_file_chunks(db, repo_id), changed_paths)

    return {
        "repo_id": str(repo_id),
        "base_sha": diff.base_sha,
        "head_sha": diff.head_sha,
        "changed_files": _summarize_changed(changed_files),
        "security_flags": _with_severity(diff.security_flags or []),
        "blast_radius": blast,
        "created_at": diff.created_at,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No commit diff available for this repository"
        )

    changed_files = diff.changed_files or []
    contexts = _diff_contexts(_rank_for_question(changed_files, payload.question))
    intent = detect_intent(payload.question)
    security_categories = sorted(
        {cat for flag in (diff.security_flags or []) for cat in (flag.get("categories") or [])}
    )

    def _fallback_text() -> str:
        summary = _summarize_changed(changed_files)
        touched = ", ".join(item["path"] for item in summary[:8]) or "no files"
        note = f" Security-sensitive areas: {', '.join(security_categories)}." if security_categories else ""
        return f"This commit ({diff.head_sha[:10]}) changed: {touched}.{note}"

    # A sync generator on purpose: Starlette iterates it in a worker thread, so the blocking
    # LLM HTTP stream never stalls the event loop.
    def event_stream():
        yield from stream_answer(
            lambda: synthesize_grounded_answer_stream(query=payload.question, contexts=contexts, intent=intent),
            _fallback_text,
            f"Diff LLM synthesis failed for repo {repo_id}",
        )

        final = {
            "head_sha": diff.head_sha,
            "base_sha": diff.base_sha,
            "security_categories": security_categories,
        }
        yield sse_event("done", final)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
