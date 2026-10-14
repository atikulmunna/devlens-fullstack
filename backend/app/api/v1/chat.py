import json
import logging
import re
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisResult, ChatMessage, CodeChunk, ChatSession, Repository, User
from app.db.session import SessionLocal
from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.deps import get_current_user, get_db_session
from app.services.citations import format_citation, validate_citations_for_repo
from app.services.chat_synthesizer import (
    ChatIntent,
    ChatSynthesisError,
    synthesize_grounded_answer_stream,
)
from app.services.retrieval_hybrid import hybrid_search_chunks, load_chunk_content

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])
CHAT_CREATE_SESSION_REQUEST_EXAMPLE = {"repo_id": "cd3ce6f7-76fc-4cc2-8e34-c176f7af6f82"}
CHAT_CREATE_SESSION_RESPONSE_EXAMPLE = {
    "session_id": "d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc",
    "repo_id": "cd3ce6f7-76fc-4cc2-8e34-c176f7af6f82",
    "created_at": "2026-02-23T13:00:00Z",
}
CHAT_SEND_MESSAGE_REQUEST_EXAMPLE = {"content": "Where is auth refresh handled?", "top_k": 5}
CHAT_SSE_SAMPLE_RESPONSE = (
    "event: delta\n"
    'data: {"token":"Relevant "}\n\n'
    "event: done\n"
    'data: {"message_id":"d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc","citations":[],"no_citation":true}\n\n'
)

class CreateChatSessionRequest(BaseModel):
    repo_id: str


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    source_citations: dict | None = None
    created_at: datetime


class ChatSessionResponse(BaseModel):
    id: str
    repo_id: str
    user_id: str
    created_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class CreateChatSessionResponse(BaseModel):
    session_id: str
    repo_id: str
    created_at: datetime


class ChatSessionListItem(BaseModel):
    id: str
    repo_id: str
    created_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionListItem] = Field(default_factory=list)


class SuggestedQuestionsResponse(BaseModel):
    repo_id: str
    suggestions: list[str] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    content: str
    top_k: int = 5


def _ensure_owned_session(db: Session, session_id: UUID, user_id: UUID) -> ChatSession:
    session_row = db.execute(select(ChatSession).where(ChatSession.id == session_id)).scalar_one_or_none()
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    if session_row.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session_row


def _normalize_language(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower()
    aliases = {
        "py": "Python",
        "python": "Python",
        "js": "JavaScript",
        "javascript": "JavaScript",
        "ts": "TypeScript",
        "tsx": "TypeScript",
        "jsx": "JavaScript (React JSX)",
        "go": "Go",
        "java": "Java",
        "rb": "Ruby",
        "rs": "Rust",
        "c": "C",
        "cpp": "C++",
        "c++": "C++",
        "cs": "C#",
        "c#": "C#",
        "php": "PHP",
        "kt": "Kotlin",
        "swift": "Swift",
        "scala": "Scala",
        "sh": "Shell",
        "bash": "Shell",
        "sql": "SQL",
        "md": "Markdown",
        "rst": "reStructuredText",
        "toml": "TOML",
        "makefile": "Makefile",
        "yml": "YAML",
        "yaml": "YAML",
        "json": "JSON",
    }
    return aliases.get(key, raw.strip())


# Documentation and configuration formats: present in most repos, but not what a project is "written in".
NON_CODE_LANGUAGES = {"Markdown", "reStructuredText", "YAML", "JSON", "TOML", "txt", "unknown"}


def _language_answer(breakdown: dict | None) -> str | None:
    """Describe the repo's code languages from the analysis breakdown (percent of indexed size)."""
    shares: dict[str, float] = {}
    for key, share in (breakdown or {}).items():
        name = _normalize_language(key)
        if name and name not in NON_CODE_LANGUAGES:
            shares[name] = shares.get(name, 0.0) + float(share or 0)
    total = sum(shares.values())
    if total <= 0:
        return None

    ranked = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)

    def _describe(name: str, share: float) -> str:
        percent = share / total * 100
        return f"{name} ({'under 1' if percent < 1 else round(percent)}%)"

    lead_name, lead_share = ranked[0]
    if len(ranked) == 1:
        return f"The code is written in {lead_name}."
    rest = ", ".join(_describe(name, share) for name, share in ranked[1:4])
    return f"The code is mostly {_describe(lead_name, lead_share)}, with {rest}. Shares are by size of the indexed code."


def _language_question(query: str) -> bool:
    # Phrases only: a bare "stack" or "language" also matches "stack trace" or "language model".
    q = query.lower()
    patterns = (
        "what language",
        "which language",
        "programming language",
        "languages",
        "tech stack",
        "built with",
        "written in",
    )
    return any(token in q for token in patterns)


def _summary_question(query: str) -> bool:
    q = query.lower()
    patterns = (
        "summarize",
        "summary",
        "high-level",
        "high level",
        "overview",
        "purpose",
        "core modules",
        "runtime flow",
        "output format",
    )
    return any(token in q for token in patterns)


def _detect_chat_intent(query: str) -> ChatIntent:
    q = query.lower()
    architecture_tokens = ("architecture", "design", "components", "module", "flow", "dependency")
    setup_tokens = ("setup", "install", "run", "start", "configure", "env", "docker", "deploy")
    debug_tokens = ("bug", "error", "failing", "exception", "debug", "issue", "fix", "broken")
    security_tokens = ("auth", "token", "permission", "secret", "security", "csrf", "oauth")
    if any(t in q for t in architecture_tokens):
        return "architecture"
    if any(t in q for t in setup_tokens):
        return "setup"
    if any(t in q for t in debug_tokens):
        return "debug"
    if any(t in q for t in security_tokens):
        return "security"
    return "general"


def _select_diverse_results(results: list[dict], limit: int = 6) -> list[dict]:
    if not results:
        return []

    def _path_weight(path: str) -> int:
        p = path.lower()
        if p.endswith("readme.md"):
            return 0
        if p.endswith(("package.json", "pyproject.toml", "requirements.txt", "go.mod", "cargo.toml")):
            return 1
        if p.endswith(("dockerfile", "docker-compose.yml", "docker-compose.yaml")):
            return 2
        if any(k in p for k in ("/main.", "/index.", "/app.", "/server.", "/cli.")):
            return 3
        if any(k in p for k in ("/src/", "/app/", "/lib/", "/core/", "/services/", "/components/")):
            return 4
        return 5

    ranked = sorted(
        enumerate(results),
        key=lambda x: (_path_weight(str(x[1].get("file_path") or "")), x[0]),
    )

    selected: list[dict] = []
    seen_paths: set[str] = set()
    seen_roots: set[str] = set()
    for _, item in ranked:
        path = str(item.get("file_path") or "")
        if not path or path in seen_paths:
            continue
        root = path.split("/", 1)[0]
        # Prefer root diversity but allow at most two per root.
        root_count = sum(
            1
            for s in selected
            if str(s.get("file_path") or "").split("/", 1)[0] == root
        )
        if root in seen_roots and root_count >= 2:
            continue
        selected.append(item)
        seen_paths.add(path)
        seen_roots.add(root)
        if len(selected) >= limit:
            break

    if len(selected) < min(limit, len(results)):
        for item in results:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= limit:
                break
    return selected


def _readme_contexts(db: Session, repo_id: UUID, limit: int = 2) -> list[dict]:
    """The opening of the root README: the best single source for what a project is, and one
    a "summarize this" query rarely retrieves on its own."""
    rows = (
        db.execute(
            select(CodeChunk)
            .where(CodeChunk.repo_id == repo_id, func.lower(CodeChunk.file_path).like("readme%"))
            .order_by(CodeChunk.file_path.asc(), CodeChunk.start_line.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "chunk_id": str(row.id),
            "file_path": row.file_path,
            "line_start": row.start_line,
            "line_end": row.end_line,
            "language": row.language,
            "content": row.content,
        }
        for row in rows
        if row.content.strip()
    ]


def _plan_assistant_response(db: Session, repo_id: UUID, query: str, results: list[dict]) -> dict:
    """Decide how to answer: a deterministic final string, or an LLM synthesis plan.

    Returns {"kind": "final", "text", "citations"} for the no-result and language branches, or
    {"kind": "llm", "contexts", "mode", "intent", "citations", "top", "refs"} when the answer
    should be synthesized (and streamed) from the model. Summary questions use the model's
    summary mode.
    """
    if _language_question(query):
        analysis = (
            db.execute(
                select(AnalysisResult).where(AnalysisResult.repo_id == repo_id).order_by(AnalysisResult.created_at.desc())
            )
            .scalars()
            .first()
        )
        answer = _language_answer(analysis.language_breakdown if analysis else None)
        if answer:
            # Whole-repository statistics, so there are no specific lines to cite.
            return {"kind": "final", "text": answer, "citations": {"citations": [], "no_citation": True}}

    if not results:
        return {
            "kind": "final",
            "text": "I could not find relevant indexed code context for that query.",
            "citations": {"citations": [], "no_citation": True},
        }

    top = results[: min(3, len(results))]
    diverse = _select_diverse_results(results, limit=min(6, len(results)))
    formatted = [
        format_citation(
            chunk_id=str(item.get("chunk_id")),
            file_path=str(item.get("file_path") or ""),
            line_start=item.get("start_line"),
            line_end=item.get("end_line"),
            score=item.get("rerank_score") if item.get("rerank_score") is not None else item.get("score"),
        )
        for item in top
    ]
    valid_citations = validate_citations_for_repo(db, repo_id=repo_id, citations=formatted)
    refs = [f"{item.get('file_path')}:{item.get('line_start') or 1}" for item in valid_citations] or ["no exact anchor"]
    citations = {
        "citations": valid_citations,
        "no_citation": len(valid_citations) == 0,
    }

    llm_contexts = []
    llm_candidates = diverse if diverse else top
    # Retrieval results carry only metadata, so load the chunk code the LLM must ground on.
    content_by_chunk = load_chunk_content(
        db,
        repo_id=repo_id,
        chunk_ids=[str(item.get("chunk_id")) for item in llm_candidates if item.get("chunk_id")],
    )
    for item in llm_candidates:
        chunk_id = str(item.get("chunk_id") or "")
        content = str(item.get("content") or content_by_chunk.get(chunk_id) or "")
        # A vector hit whose chunk row is gone (stale index) has no code to ground on.
        if not content.strip():
            continue
        llm_contexts.append(
            {
                "chunk_id": chunk_id,
                "file_path": item.get("file_path"),
                "line_start": item.get("start_line"),
                "line_end": item.get("end_line"),
                "language": item.get("language"),
                "content": content,
            }
        )
    mode = "summary" if _summary_question(query) else "answer"
    if mode == "summary":
        readme = _readme_contexts(db, repo_id)
        readme_ids = {context["chunk_id"] for context in readme}
        llm_contexts = readme + [context for context in llm_contexts if context["chunk_id"] not in readme_ids]
    return {
        "kind": "llm",
        "contexts": llm_contexts,
        "mode": mode,
        "intent": _detect_chat_intent(query),
        "citations": citations,
        "top": top,
        "refs": refs,
    }


def _snippet_fallback_text(db: Session, repo_id: UUID, top: list[dict], refs: list[str]) -> str:
    """Deterministic answer used when LLM synthesis is unavailable or empty."""
    snippets: list[str] = []
    content_by_chunk = load_chunk_content(
        db,
        repo_id=repo_id,
        chunk_ids=[str(item.get("chunk_id")) for item in top if item.get("chunk_id")],
    )
    for item in top:
        path = str(item.get("file_path") or "")
        line = item.get("start_line") or 1
        chunk_id = str(item.get("chunk_id") or "")
        raw_content = str(item.get("content") or content_by_chunk.get(chunk_id) or "").strip()
        preview = re.sub(r"\s+", " ", raw_content)[:120]
        if preview:
            snippets.append(f"{path}:{line} -> {preview}")
        else:
            snippets.append(f"{path}:{line}")

    if snippets:
        return "Based on indexed code context: " + " | ".join(snippets) + "."
    return "Relevant code context was found in: " + ", ".join(refs) + "."


def _build_suggested_questions(db: Session, repo_id: UUID, limit: int) -> list[str]:
    file_rows = db.execute(
        select(CodeChunk.file_path)
        .where(CodeChunk.repo_id == repo_id)
        .distinct()
        .order_by(CodeChunk.file_path.asc())
        .limit(3)
    ).all()
    files = [row[0] for row in file_rows if row and row[0]]

    suggestions = [
        "What are the main architecture components in this repository?",
        "Where is authentication and token handling implemented?",
        "Which files show the core business logic flow?",
    ]
    for path in files:
        suggestions.append(f"Explain the responsibilities of `{path}`.")
    return suggestions[: max(1, min(limit, 10))]


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    summary="List chat sessions",
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def list_chat_sessions(
    repo_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionListResponse:
    query = select(ChatSession).where(ChatSession.user_id == current_user.id).order_by(ChatSession.created_at.desc())
    if repo_id is not None:
        query = query.where(ChatSession.repo_id == repo_id)

    sessions = db.execute(query).scalars().all()
    payload: list[ChatSessionListItem] = []
    for row in sessions:
        messages = db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == row.id)
            .order_by(ChatMessage.created_at.desc())
        ).scalars().all()
        last_preview = messages[0].content[:120] if messages else None
        payload.append(
            ChatSessionListItem(
                id=str(row.id),
                repo_id=str(row.repo_id),
                created_at=row.created_at,
                message_count=len(messages),
                last_message_preview=last_preview,
            )
        )
    return ChatSessionListResponse(sessions=payload)


@router.post(
    "/sessions",
    response_model=CreateChatSessionResponse,
    summary="Create chat session",
    responses={
        200: {"content": {"application/json": {"example": CHAT_CREATE_SESSION_RESPONSE_EXAMPLE}}},
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": CHAT_CREATE_SESSION_REQUEST_EXAMPLE,
                }
            }
        }
    },
)
def create_chat_session(
    payload: CreateChatSessionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> CreateChatSessionResponse:
    try:
        repo_uuid = UUID(payload.repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid repo_id") from exc

    repo = db.execute(select(Repository).where(Repository.id == repo_uuid)).scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    row = ChatSession(id=uuid4(), repo_id=repo.id, user_id=current_user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return CreateChatSessionResponse(session_id=str(row.id), repo_id=str(row.repo_id), created_at=row.created_at)


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Get session with message history",
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def get_chat_session(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    session_row = _ensure_owned_session(db, session_id, current_user.id)
    message_rows = db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_row.id).order_by(ChatMessage.created_at.asc())
    ).scalars().all()
    messages = [
        ChatMessageResponse(
            id=str(msg.id),
            role=msg.role,
            content=msg.content,
            source_citations=msg.source_citations,
            created_at=msg.created_at,
        )
        for msg in message_rows
    ]
    return ChatSessionResponse(
        id=str(session_row.id),
        repo_id=str(session_row.repo_id),
        user_id=str(session_row.user_id),
        created_at=session_row.created_at,
        messages=messages,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete chat session",
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def delete_chat_session(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    session_row = _ensure_owned_session(db, session_id, current_user.id)
    db.query(ChatMessage).filter(ChatMessage.session_id == session_row.id).delete(synchronize_session=False)
    db.delete(session_row)
    db.commit()


@router.get(
    "/repos/{repo_id}/suggestions",
    response_model=SuggestedQuestionsResponse,
    summary="Suggested chat questions for a repository",
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def suggested_questions(
    repo_id: UUID,
    limit: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> SuggestedQuestionsResponse:
    _ = current_user
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    return SuggestedQuestionsResponse(repo_id=str(repo_id), suggestions=_build_suggested_questions(db, repo_id, limit))


@router.post(
    "/sessions/{session_id}/message",
    summary="Send message and stream assistant response (SSE)",
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}, "example": CHAT_SSE_SAMPLE_RESPONSE}}},
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": CHAT_SEND_MESSAGE_REQUEST_EXAMPLE,
                }
            }
        }
    },
)
def send_chat_message(
    session_id: UUID,
    payload: SendMessageRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if not payload.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message content must not be empty")

    session_row = _ensure_owned_session(db, session_id, current_user.id)

    user_msg = ChatMessage(
        id=uuid4(),
        session_id=session_row.id,
        role="user",
        content=payload.content.strip(),
        source_citations=None,
    )
    db.add(user_msg)
    # Commit the user turn now: the assistant is persisted later inside the streaming
    # generator, by which point this request's DB session may already be torn down, so a
    # flush alone would be rolled back and the user message lost.
    db.commit()

    results = hybrid_search_chunks(db, repo_id=session_row.repo_id, query=payload.content, limit=payload.top_k)
    plan = _plan_assistant_response(db, session_row.repo_id, payload.content, results)
    citations = plan["citations"]

    repo_id = session_row.repo_id

    def _delta(token: str) -> str:
        return f"event: delta\ndata: {json.dumps({'token': token})}\n\n"

    # A sync generator on purpose: Starlette iterates it in a worker thread, so the blocking
    # LLM HTTP stream never stalls the event loop. The request's `db` is closed by the time
    # this runs, so any DB work here uses its own session.
    def event_stream():
        # Deterministic branches (no results / language) emit their fixed text.
        if plan["kind"] == "final":
            final_text = plan["text"]
            for token in final_text.split(" "):
                yield _delta(token + " ")
        else:
            # LLM branch: stream real tokens as they arrive from the model.
            parts: list[str] = []
            try:
                for piece in synthesize_grounded_answer_stream(
                    query=payload.content,
                    contexts=plan["contexts"],
                    mode=plan["mode"],
                    intent=plan["intent"],
                ):
                    parts.append(piece)
                    yield _delta(piece)
            except ChatSynthesisError as exc:
                # A mid-stream failure keeps whatever partial text was already delivered.
                logger.warning("Chat LLM synthesis failed for session %s: %s", session_id, exc)

            final_text = "".join(parts).strip()
            if not final_text:
                # Nothing streamed (all providers failed before emitting): fall back.
                with SessionLocal() as stream_db:
                    final_text = _snippet_fallback_text(stream_db, repo_id, plan["top"], plan["refs"])
                for token in final_text.split(" "):
                    yield _delta(token + " ")

        message_id = uuid4()
        with SessionLocal() as stream_db:
            stream_db.add(
                ChatMessage(
                    id=message_id,
                    session_id=session_id,
                    role="assistant",
                    content=final_text,
                    source_citations=citations,
                )
            )
            stream_db.commit()

        final = {
            "message_id": str(message_id),
            "citations": citations.get("citations", []),
            "no_citation": bool(citations.get("no_citation")),
        }
        yield f"event: done\ndata: {json.dumps(final)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
