from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.api.sse import SSE_HEADERS, sse_event, stream_answer, stream_text
from app.db.models import ChatMessage, ChatSession, User
from app.db.session import SessionLocal
from app.deps import get_current_user, get_db_session, get_repo_or_404
from app.services.chat_planner import build_suggested_questions, plan_answer, snippet_fallback_text
from app.services.chat_synthesizer import (
    synthesize_grounded_answer_stream,
)
from app.services.citations import mark_cited
from app.services.retrieval_hybrid import hybrid_search_chunks

router = APIRouter(prefix="/chat", tags=["chat"])
# Earlier messages sent to the model with each question: three question and answer turns.
HISTORY_MESSAGES = 6
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


def _recent_history(db: Session, session_id: UUID) -> list[dict]:
    rows = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_MESSAGES)
        )
        .scalars()
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in reversed(rows)]


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
    # One statement: each session's message count and latest message come from correlated subqueries
    # (served by idx_chat_messages_session_created) instead of a query per session.
    in_session = ChatMessage.session_id == ChatSession.id
    message_count = select(func.count()).where(in_session).correlate(ChatSession).scalar_subquery()
    latest_message = (
        select(ChatMessage.content)
        .where(in_session)
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    query = (
        select(ChatSession, message_count, latest_message)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    if repo_id is not None:
        query = query.where(ChatSession.repo_id == repo_id)

    sessions = [
        ChatSessionListItem(
            id=str(row.id),
            repo_id=str(row.repo_id),
            created_at=row.created_at,
            message_count=count,
            last_message_preview=latest[:120] if latest else None,
        )
        for row, count, latest in db.execute(query).all()
    ]
    return ChatSessionListResponse(sessions=sessions)


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

    repo = get_repo_or_404(db, repo_uuid)

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
    message_rows = (
        db.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_row.id).order_by(ChatMessage.created_at.asc())
        )
        .scalars()
        .all()
    )
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
    get_repo_or_404(db, repo_id)

    return SuggestedQuestionsResponse(repo_id=str(repo_id), suggestions=build_suggested_questions(db, repo_id, limit))


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
    # Read before saving this question, so the history holds earlier turns only.
    history = _recent_history(db, session_row.id)

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
    plan = plan_answer(db, session_row.repo_id, payload.content, results)
    citations = plan["citations"]

    repo_id = session_row.repo_id

    # A sync generator on purpose: Starlette iterates it in a worker thread, so the blocking
    # LLM HTTP stream never stalls the event loop. The request's `db` is closed by the time
    # this runs, so any DB work here uses its own session.
    def event_stream():
        if plan["kind"] == "final":
            # Deterministic branches (no results / language) emit their fixed text.
            final_text = plan["text"]
            yield from stream_text(final_text)
        else:

            def snippet_fallback() -> str:
                with SessionLocal() as stream_db:
                    return snippet_fallback_text(stream_db, repo_id, plan["top"], plan["refs"])

            final_text = yield from stream_answer(
                lambda: synthesize_grounded_answer_stream(
                    query=payload.content,
                    contexts=plan["contexts"],
                    mode=plan["mode"],
                    intent=plan["intent"],
                    history=history,
                ),
                snippet_fallback,
                f"Chat LLM synthesis failed for session {session_id}",
            )

        final_citations = {**citations, "citations": mark_cited(citations.get("citations", []), final_text)}
        message_id = uuid4()
        with SessionLocal() as stream_db:
            stream_db.add(
                ChatMessage(
                    id=message_id,
                    session_id=session_id,
                    role="assistant",
                    content=final_text,
                    source_citations=final_citations,
                )
            )
            stream_db.commit()

        final = {
            "message_id": str(message_id),
            "citations": final_citations["citations"],
            "no_citation": bool(final_citations.get("no_citation")),
        }
        yield sse_event("done", final)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
