from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.db.models import AnalysisResult, Repository, ShareToken, User
from app.deps import get_current_user, get_db_session
from app.services.share_tokens import create_share_token, decode_share_token, new_share_token_id, share_token_expiry

router = APIRouter(prefix="/export", tags=["export"])
public_router = APIRouter(prefix="/share", tags=["share"])
SHARE_CREATE_REQUEST_EXAMPLE = {"ttl_days": 7}
SHARE_CREATE_RESPONSE_EXAMPLE = {
    "share_id": "d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc",
    "share_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "share_url": "http://localhost:3000/share/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_at": "2026-03-01T12:00:00Z",
}
SHARE_RESOLVE_RESPONSE_EXAMPLE = {
    "repo_id": "cd3ce6f7-76fc-4cc2-8e34-c176f7af6f82",
    "repository": {
        "github_url": "https://github.com/owner/repo",
        "full_name": "owner/repo",
        "owner": "owner",
        "name": "repo",
        "description": "Example repository",
        "stars": 120,
        "forks": 20,
        "language": "Python",
        "default_branch": "main",
        "latest_commit_sha": "abcdef123",
    },
    "analysis": {
        "quality_score": 74,
        "architecture_summary": "Service-oriented modules...",
        "language_breakdown": {"Python": 80, "TypeScript": 20},
        "contributor_stats": {"total": 7},
        "tech_debt_flags": {"todo": 14, "fixme": 3},
        "file_tree": {"type": "dir", "name": "/", "children": []},
    },
    "shared_at": "2026-02-23T12:00:00Z",
    "expires_at": "2026-03-01T12:00:00Z",
}

class ShareCreateRequest(BaseModel):
    ttl_days: int | None = None


class ShareCreateResponse(BaseModel):
    share_id: str
    share_token: str
    share_url: str
    expires_at: datetime


class SharedAnalysisResponse(BaseModel):
    repo_id: str
    repository: dict
    analysis: dict
    shared_at: datetime
    expires_at: datetime


def _get_repo_or_404(db: Session, repo_id: UUID) -> Repository:
    repo = db.execute(select(Repository).where(Repository.id == repo_id)).scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repo


def _get_latest_result_or_404(db: Session, repo_id: UUID) -> AnalysisResult:
    result = db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.repo_id == repo_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    ).scalars().first()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis result not found")
    return result


@router.post(
    "/{repo_id}/share",
    response_model=ShareCreateResponse,
    summary="Create signed public share link",
    responses={
        200: {"content": {"application/json": {"example": SHARE_CREATE_RESPONSE_EXAMPLE}}},
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": SHARE_CREATE_REQUEST_EXAMPLE,
                }
            }
        }
    },
)
def create_share_link(
    repo_id: UUID,
    payload: ShareCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ShareCreateResponse:
    _get_repo_or_404(db, repo_id)
    _get_latest_result_or_404(db, repo_id)

    share_id = new_share_token_id()
    expires_at = share_token_expiry(payload.ttl_days)
    token = create_share_token(repo_id=repo_id, share_id=share_id, expires_at=expires_at)

    db.add(
        ShareToken(
            id=share_id,
            repo_id=repo_id,
            user_id=current_user.id,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    db.commit()

    share_url = f"{str(settings.frontend_url).rstrip('/')}/share/{token}"
    return ShareCreateResponse(
        share_id=str(share_id),
        share_token=token,
        share_url=share_url,
        expires_at=expires_at,
    )


@router.delete(
    "/share/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke existing share link",
    responses={
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def revoke_share_link(
    share_id: UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    row = db.execute(select(ShareToken).where(ShareToken.id == share_id)).scalar_one_or_none()
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.commit()


@public_router.get(
    "/{token}",
    response_model=SharedAnalysisResponse,
    summary="Resolve public share token",
    responses={
        200: {"content": {"application/json": {"example": SHARE_RESOLVE_RESPONSE_EXAMPLE}}},
        401: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def get_shared_analysis(token: str, db: Session = Depends(get_db_session)) -> SharedAnalysisResponse:
    payload = decode_share_token(token)

    try:
        share_id = UUID(str(payload["jti"]))
        repo_id = UUID(str(payload["sub"]))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid share token payload") from exc

    row = db.execute(select(ShareToken).where(ShareToken.id == share_id)).scalar_one_or_none()
    if row is None or row.repo_id != repo_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid share token")
    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Share token revoked")
    if row.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Share token expired")

    repo = _get_repo_or_404(db, repo_id)
    result = _get_latest_result_or_404(db, repo_id)
    return SharedAnalysisResponse(
        repo_id=str(repo.id),
        repository={
            "github_url": repo.github_url,
            "full_name": repo.full_name,
            "owner": repo.owner,
            "name": repo.name,
            "description": repo.description,
            "stars": repo.stars,
            "forks": repo.forks,
            "language": repo.language,
            "default_branch": repo.default_branch,
            "latest_commit_sha": repo.latest_commit_sha,
        },
        analysis={
            "quality_score": result.quality_score,
            "architecture_summary": result.architecture_summary,
            "language_breakdown": result.language_breakdown or {},
            "contributor_stats": result.contributor_stats or {},
            "tech_debt_flags": result.tech_debt_flags or {},
            "file_tree": result.file_tree or {},
        },
        shared_at=row.created_at,
        expires_at=row.expires_at,
    )
