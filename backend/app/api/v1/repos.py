import asyncio
import json
import time
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisJob, AnalysisResult, Repository
from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.deps import get_db_session
from app.db.session import SessionLocal
from app.services.github_repos import resolve_public_repo_snapshot
from app.services.retrieval_hybrid import hybrid_search_chunks
from app.services.retrieval_lexical import lexical_search_chunks
from app.observability import observe_sse_startup, trace_span

router = APIRouter(prefix="/repos", tags=["repos"])

ACTIVE_STATUSES = {"queued", "cloning", "parsing", "embedding", "analyzing"}
ANALYZE_REQUEST_EXAMPLE = {
    "github_url": "https://github.com/owner/repo",
    "force_reanalyze": False,
}
ANALYZE_RESPONSE_EXAMPLE = {
    "job_id": "d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc",
    "repo_id": "cd3ce6f7-76fc-4cc2-8e34-c176f7af6f82",
    "status": "queued",
    "cache_hit": False,
    "commit_sha": "abcdef1234567890",
}
SSE_SAMPLE_RESPONSE = (
    "event: progress\n"
    'data: {"job_id":"d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc","stage":"parsing","progress":35,"message":"parsing in progress","eta_seconds":null}\n\n'
    "event: done\n"
    'data: {"job_id":"d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc","stage":"done","progress":100}\n\n'
)


class AnalyzeRepoRequest(BaseModel):
    github_url: str = Field(..., examples=["https://github.com/owner/repo"])
    force_reanalyze: bool = False


class AnalyzeRepoResponse(BaseModel):
    job_id: str
    repo_id: str
    status: str
    cache_hit: bool
    commit_sha: str


class LexicalSearchChunk(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    score: float


class LexicalSearchResponse(BaseModel):
    repo_id: str
    query: str
    total: int
    results: list[LexicalSearchChunk]


class HybridSearchChunk(BaseModel):
    chunk_id: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    dense_score: float
    lexical_score: float
    rerank_score: float


class HybridSearchResponse(BaseModel):
    repo_id: str
    query: str
    total: int
    results: list[HybridSearchChunk]


class DashboardRepositoryResponse(BaseModel):
    id: str
    github_url: str
    full_name: str
    owner: str
    name: str
    default_branch: str
    latest_commit_sha: str | None = None
    description: str | None = None
    stars: int | None = None
    forks: int | None = None
    language: str | None = None
    size_kb: int | None = None


class DashboardResponse(BaseModel):
    repo_id: str
    repository: DashboardRepositoryResponse
    analysis: dict | None = None
    has_analysis: bool


def _fetch_latest_job(db: Session, repo_id: UUID) -> AnalysisJob | None:
    return (
        db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.repo_id == repo_id)
            .order_by(AnalysisJob.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _build_event_payload(job: AnalysisJob) -> tuple[str, dict]:
    if job.status == "failed":
        code = "UNKNOWN"
        message = job.error_message or "Job failed"
        if job.error_message and ":" in job.error_message:
            code, message = [part.strip() for part in job.error_message.split(":", 1)]

        return "error", {
            "job_id": str(job.id),
            "stage": "failed",
            "progress": int(job.progress or 100),
            "code": code,
            "message": message,
        }

    if job.status == "done":
        return "done", {
            "job_id": str(job.id),
            "stage": "done",
            "progress": 100,
        }

    return "progress", {
        "job_id": str(job.id),
        "stage": job.status,
        "progress": int(job.progress or 0),
        "message": f"{job.status} in progress",
        "eta_seconds": None,
    }


def _upsert_repository(db: Session, snapshot: dict) -> Repository:
    repo = db.execute(select(Repository).where(Repository.full_name == snapshot["full_name"])).scalar_one_or_none()
    if repo is None:
        repo = Repository(
            id=uuid4(),
            github_url=snapshot["github_url"],
            full_name=snapshot["full_name"],
            owner=snapshot["owner"],
            name=snapshot["name"],
        )
        db.add(repo)

    repo.github_url = snapshot["github_url"]
    repo.owner = snapshot["owner"]
    repo.name = snapshot["name"]
    repo.default_branch = snapshot["default_branch"]
    repo.latest_commit_sha = snapshot["commit_sha"]
    repo.description = snapshot["description"]
    repo.stars = snapshot["stars"]
    repo.forks = snapshot["forks"]
    repo.language = snapshot["language"]
    repo.size_kb = snapshot["size_kb"]

    db.flush()
    return repo


@router.post(
    "/analyze",
    response_model=AnalyzeRepoResponse,
    summary="Create or reuse repository analysis job",
    description=(
        "Resolves latest repository metadata and head commit from GitHub. "
        "Returns an existing active/done job when dedupe conditions are met."
    ),
    responses={
        200: {
            "description": "Job created or existing job returned",
            "content": {"application/json": {"example": ANALYZE_RESPONSE_EXAMPLE}},
        },
        400: {
            "description": "Invalid GitHub URL or unsupported repository",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        502: {
            "description": "Upstream GitHub API failure",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": ANALYZE_REQUEST_EXAMPLE,
                }
            }
        }
    },
)
def analyze_repo(
    payload: AnalyzeRepoRequest,
    db: Session = Depends(get_db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    with trace_span("repos.analyze", github_url=payload.github_url):
        snapshot = resolve_public_repo_snapshot(payload.github_url)
    repo = _upsert_repository(db, snapshot)
    commit_sha = snapshot["commit_sha"]

    if not payload.force_reanalyze:
        if idempotency_key:
            by_key = db.execute(
                select(AnalysisJob)
                .where(
                    AnalysisJob.repo_id == repo.id,
                    AnalysisJob.commit_sha == commit_sha,
                    AnalysisJob.idempotency_key == idempotency_key,
                )
                .order_by(AnalysisJob.created_at.desc())
            ).scalar_one_or_none()
            if by_key:
                return AnalyzeRepoResponse(
                    job_id=str(by_key.id),
                    repo_id=str(repo.id),
                    status=by_key.status,
                    cache_hit=by_key.status == "done",
                    commit_sha=commit_sha,
                )

        by_commit = db.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.repo_id == repo.id,
                AnalysisJob.commit_sha == commit_sha,
                AnalysisJob.status.in_(ACTIVE_STATUSES | {"done"}),
            )
            .order_by(AnalysisJob.created_at.desc())
        ).scalar_one_or_none()

        if by_commit:
            return AnalyzeRepoResponse(
                job_id=str(by_commit.id),
                repo_id=str(repo.id),
                status=by_commit.status,
                cache_hit=by_commit.status == "done",
                commit_sha=commit_sha,
            )

    new_job = AnalysisJob(
        id=uuid4(),
        repo_id=repo.id,
        user_id=None,
        idempotency_key=idempotency_key,
        commit_sha=commit_sha,
        status="queued",
        progress=0,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    return AnalyzeRepoResponse(
        job_id=str(new_job.id),
        repo_id=str(repo.id),
        status=new_job.status,
        cache_hit=False,
        commit_sha=commit_sha,
    )


@router.get(
    "/{repo_id}/search/lexical",
    response_model=LexicalSearchResponse,
    summary="Lexical search over repository chunks (PostgreSQL FTS)",
    description=(
        "Runs keyword search using PostgreSQL full-text search and ranks matches with ts_rank_cd. "
        "Results are scoped to the provided repo_id."
    ),
    responses={
        400: {
            "description": "Invalid query",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        404: {
            "description": "Repository not found",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def search_repo_lexical(repo_id: UUID, q: str, limit: int = 20, db: Session = Depends(get_db_session)) -> LexicalSearchResponse:
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    results = lexical_search_chunks(db, repo_id=repo_id, query=q, limit=limit)
    return LexicalSearchResponse(repo_id=str(repo_id), query=q, total=len(results), results=results)


@router.get(
    "/{repo_id}/search/hybrid",
    response_model=HybridSearchResponse,
    summary="Hybrid search (dense + lexical + rerank)",
    description=(
        "Runs dense retrieval in Qdrant and lexical retrieval in PostgreSQL, merges candidates, "
        "then applies deterministic reranking."
    ),
    responses={
        400: {
            "description": "Invalid query",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        404: {
            "description": "Repository not found",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        502: {
            "description": "Upstream vector search failure",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def search_repo_hybrid(repo_id: UUID, q: str, limit: int = 20, db: Session = Depends(get_db_session)) -> HybridSearchResponse:
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    results = hybrid_search_chunks(db, repo_id=repo_id, query=q, limit=limit)
    return HybridSearchResponse(repo_id=str(repo_id), query=q, total=len(results), results=results)


@router.get(
    "/{repo_id}/dashboard",
    response_model=DashboardResponse,
    summary="Repository dashboard payload",
    description=(
        "Returns repository metadata and latest analysis result to render the dashboard panels "
        "(overview, architecture summary, tech debt, quality score, contributors, file explorer)."
    ),
    responses={
        404: {
            "description": "Repository not found",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def get_repo_dashboard(repo_id: UUID, db: Session = Depends(get_db_session)) -> DashboardResponse:
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    result = db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.repo_id == repo.id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    ).scalars().first()

    analysis_payload: dict | None = None
    if result is not None:
        analysis_payload = {
            "quality_score": result.quality_score,
            "architecture_summary": result.architecture_summary,
            "language_breakdown": result.language_breakdown,
            "contributor_stats": result.contributor_stats,
            "tech_debt_flags": result.tech_debt_flags,
            "file_tree": result.file_tree,
            "created_at": result.created_at,
        }

    return DashboardResponse(
        repo_id=str(repo.id),
        repository=DashboardRepositoryResponse(
            id=str(repo.id),
            github_url=repo.github_url,
            full_name=repo.full_name,
            owner=repo.owner,
            name=repo.name,
            default_branch=repo.default_branch,
            latest_commit_sha=repo.latest_commit_sha,
            description=repo.description,
            stars=repo.stars,
            forks=repo.forks,
            language=repo.language,
            size_kb=repo.size_kb,
        ),
        analysis=analysis_payload,
        has_analysis=result is not None,
    )


@router.get(
    "/{repo_id}/status",
    summary="Stream repository analysis status (SSE)",
    description=(
        "Server-Sent Events endpoint emitting `progress`, `done`, or `error` events. "
        "Use `once=true` to get a single snapshot and close the stream."
    ),
    responses={
        200: {
            "description": "SSE stream payload",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": SSE_SAMPLE_RESPONSE,
                }
            },
        },
        404: {
            "description": "Repository not found",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
async def stream_repo_status(repo_id: UUID, once: bool = False):
    with SessionLocal() as db:
        repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
        if repo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    if once:
        with SessionLocal() as db:
            job = _fetch_latest_job(db, repo_id)
        if job is None:
            payload = {"repo_id": str(repo_id), "code": "NO_JOB", "message": "No analysis job found for repository"}
            body = f"event: error\ndata: {json.dumps(payload)}\n\n"
            return PlainTextResponse(body, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

        event, payload = _build_event_payload(job)
        body = f"event: {event}\ndata: {json.dumps(payload)}\n\n"
        return PlainTextResponse(body, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    async def event_stream():
        stream_started = time.perf_counter()
        sent_first_event = False
        last_signature: tuple[str, int, str | None] | None = None
        while True:
            with SessionLocal() as db:
                job = _fetch_latest_job(db, repo_id)
            if job is None:
                payload = {"repo_id": str(repo_id), "code": "NO_JOB", "message": "No analysis job found for repository"}
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
                return

            signature = (job.status, int(job.progress or 0), job.error_message)
            if signature != last_signature or once:
                event, payload = _build_event_payload(job)
                if not sent_first_event:
                    observe_sse_startup("/api/v1/repos/{repo_id}/status", time.perf_counter() - stream_started)
                    sent_first_event = True
                yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"
                last_signature = signature

                if once or event in {"done", "error"}:
                    return

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
