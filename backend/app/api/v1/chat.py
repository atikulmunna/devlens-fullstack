import asyncio
import json
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, CodeChunk, ChatSession, Repository, User
from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.deps import get_current_user, get_db_session
from app.services.citations import format_citation, validate_citations_for_repo
from app.services.retrieval_hybrid import hybrid_search_chunks

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


def _render_assistant_response(db: Session, repo_id: UUID, results: list[dict]) -> tuple[str, dict]:
    if not results:
        citations = {"citations": [], "no_citation": True}
        return "I could not find relevant indexed code context for that query.", citations

    top = results[: min(3, len(results))]
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
    content = "Relevant code was found in: " + ", ".join(refs) + "."
    citations = {
        "citations": valid_citations,
        "no_citation": len(valid_citations) == 0,
    }
    return content, citations


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
    db.flush()

    results = hybrid_search_chunks(db, repo_id=session_row.repo_id, query=payload.content, limit=payload.top_k)
    assistant_text, citations = _render_assistant_response(db, session_row.repo_id, results)

    assistant_msg = ChatMessage(
        id=uuid4(),
        session_id=session_row.id,
        role="assistant",
        content=assistant_text,
        source_citations=citations,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    async def event_stream():
        for token in assistant_text.split(" "):
            delta = {"token": token + " "}
            yield f"event: delta\ndata: {json.dumps(delta)}\n\n"
            await asyncio.sleep(0)

        final = {
            "message_id": str(assistant_msg.id),
            "citations": citations.get("citations", []),
            "no_citation": bool(citations.get("no_citation")),
        }
        yield f"event: done\ndata: {json.dumps(final)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
