import asyncio
import json
import re
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import AnalysisResult, ChatMessage, CodeChunk, ChatSession, Repository, User
from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.deps import get_current_user, get_db_session
from app.services.citations import format_citation, validate_citations_for_repo
from app.services.chat_synthesizer import ChatIntent, ChatSynthesisError, synthesize_grounded_answer
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
        "yml": "YAML",
        "yaml": "YAML",
        "json": "JSON",
    }
    return aliases.get(key, raw.strip())


def _language_question(query: str) -> bool:
    q = query.lower()
    patterns = (
        "language",
        "languages",
        "tech stack",
        "stack",
        "what is this built with",
        "what is this written in",
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


def _fallback_repo_summary(
    repo: Repository | None,
    analysis: AnalysisResult | None,
    languages: list[str],
    top_paths: list[str],
) -> str:
    repo_name = repo.full_name if repo else "this repository"
    purpose = analysis.architecture_summary.strip() if analysis and analysis.architecture_summary else ""
    if purpose:
        purpose = re.sub(r"\s+", " ", purpose)[:180]
    else:
        purpose = f"Codebase for {repo_name}."

    modules = []
    common_roots = {"src", "app", "lib", "packages"}
    for path in top_paths:
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        root = parts[0].strip()
        candidate = root
        if root in common_roots and len(parts) > 1:
            candidate = f"{root}/{parts[1].strip()}"
        if candidate and candidate not in modules:
            modules.append(candidate)
        if len(modules) >= 5:
            break
    module_text = ", ".join(modules) if modules else "main source and support modules"

    language_text = ", ".join(languages[:6]) if languages else (repo.language or "not clearly identified")

    output_hints = []
    for path in top_paths:
        lower = path.lower()
        if "gif" in lower and "GIF" not in output_hints:
            output_hints.append("GIF")
        if "webp" in lower and "WebP" not in output_hints:
            output_hints.append("WebP")
        if "dataurl" in lower and "data URL" not in output_hints:
            output_hints.append("data URL")
    if any(path.lower().endswith((".html", ".tsx", ".jsx", ".vue", ".svelte")) for path in top_paths):
        output_hints.append("web UI views")
    if any(path.lower().endswith((".json", ".yaml", ".yml")) for path in top_paths):
        output_hints.append("structured config/data")
    output_text = ", ".join(dict.fromkeys(output_hints)) if output_hints else "runtime artifacts inferred from code paths"

    flow_hints: list[str] = []
    lower_paths = [p.lower() for p in top_paths]
    if any("cli" in p or "argparse" in p or "typer" in p for p in lower_paths):
        flow_hints.append("CLI entrypoint receives arguments")
    if any("api" in p or "route" in p or "controller" in p for p in lower_paths):
        flow_hints.append("request handlers call service modules")
    if any("component" in p or "react" in p or p.endswith(".tsx") for p in lower_paths):
        flow_hints.append("UI components render feature views")
    if any("service" in p or "core" in p or "engine" in p for p in lower_paths):
        flow_hints.append("core modules execute main business logic")
    runtime_flow = (
        "; ".join(flow_hints[:3]) + "."
        if flow_hints
        else "entrypoint initializes modules, then feature components/services process the main workflow."
    )

    bullets = [
        f"- Purpose: {purpose}",
        f"- Core modules: {module_text}.",
        f"- Runtime flow: {runtime_flow}",
        f"- Output formats: {output_text}.",
        f"- Primary languages: {language_text}.",
    ]
    return "\n".join(bullets)


def _normalize_summary_text(raw: str) -> str:
    text = (raw or "").replace("\r", "\n").strip()
    if not text:
        return text

    # Remove ingestion/pipeline noise globally before formatting.
    text = re.sub(
        r"\s*The parse/index stage identified[^.\n]*(?:[.\n]|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*Representative paths include:[^.\n]*(?:[.\n]|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Force known summary sections onto their own bullet lines.
    text = re.sub(
        r"\s-\s(?=(Purpose|Core modules|Runtime flow|Output formats|Primary languages):)",
        "\n- ",
        text,
        flags=re.IGNORECASE,
    )

    # Convert remaining inline " - Section: ..." segments to line bullets.
    text = re.sub(r"\s-\s(?=[A-Z][^:]{1,40}:)", "\n- ", text)

    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            lines.append(stripped)
            continue
        if stripped.startswith("-"):
            lines.append(f"- {stripped[1:].strip()}")
            continue
        if re.match(r"^[A-Z][^:]{1,40}:", stripped):
            lines.append(f"- {stripped}")
            continue
        if lines:
            lines[-1] = f"{lines[-1]} {stripped}"
        else:
            lines.append(f"- {stripped}")

    def _clean_purpose_bullet(line: str) -> str:
        if not line.lower().startswith("- purpose:"):
            return line
        text = line[len("- Purpose:"):].strip()
        text = re.sub(r"\s*The parse/index stage identified[^.]*\.?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*Representative paths include:[^.]*\.?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" .")
        if not text:
            text = "This repository appears to implement its main product features."
        if len(text) > 170:
            cut = text.rfind(" ", 0, 170)
            text = text[:cut if cut > 0 else 170].rstrip()
        return f"- Purpose: {text}."

    lines = [_clean_purpose_bullet(line) for line in lines]

    # Cap verbosity while preserving requested format.
    return "\n".join(lines[:6])


def _render_assistant_response(db: Session, repo_id: UUID, query: str, results: list[dict]) -> tuple[str, dict]:
    if not results:
        citations = {"citations": [], "no_citation": True}
        return "I could not find relevant indexed code context for that query.", citations

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
    content = "Relevant code was found in: " + ", ".join(refs) + "."
    citations = {
        "citations": valid_citations,
        "no_citation": len(valid_citations) == 0,
    }

    if _language_question(query):
        languages: list[str] = []
        for item in results:
            normalized = _normalize_language(item.get("language"))
            if normalized and normalized not in languages:
                languages.append(normalized)
            if len(languages) >= 8:
                break
        if languages:
            if len(languages) == 1:
                content = f"The indexed code appears to be primarily {languages[0]}."
            else:
                content = "The indexed code appears to use: " + ", ".join(languages) + "."
            if refs:
                content += " Evidence from: " + ", ".join(refs) + "."
            return content, citations

    if _summary_question(query):
        repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
        analysis = (
            db.execute(select(AnalysisResult).where(AnalysisResult.repo_id == repo_id).order_by(AnalysisResult.created_at.desc()))
            .scalars()
            .first()
        )

        langs: list[str] = []
        for item in results:
            normalized = _normalize_language(item.get("language"))
            if normalized and normalized not in langs:
                langs.append(normalized)

        top_paths = [str(item.get("file_path") or "") for item in results[:8] if item.get("file_path")]
        summary = _fallback_repo_summary(repo=repo, analysis=analysis, languages=langs, top_paths=top_paths)
        return _normalize_summary_text(summary), citations

    llm_contexts = []
    llm_candidates = diverse if diverse else top
    for item in llm_candidates:
        chunk_id = str(item.get("chunk_id") or "")
        llm_contexts.append(
            {
                "chunk_id": chunk_id,
                "file_path": item.get("file_path"),
                "line_start": item.get("start_line"),
                "line_end": item.get("end_line"),
                "language": item.get("language"),
                "content": str(item.get("content") or ""),
            }
        )
    try:
        synthesized = synthesize_grounded_answer(
            query=query,
            contexts=llm_contexts,
            intent=_detect_chat_intent(query),
        )
        if synthesized.strip():
            return synthesized.strip(), citations
    except ChatSynthesisError:
        pass

    snippets: list[str] = []
    content_by_chunk = _load_chunk_content(
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
        content = "Based on indexed code context: " + " | ".join(snippets) + "."
    else:
        content = "Relevant code context was found in: " + ", ".join(refs) + "."
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
    assistant_text, citations = _render_assistant_response(db, session_row.repo_id, payload.content, results)

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
