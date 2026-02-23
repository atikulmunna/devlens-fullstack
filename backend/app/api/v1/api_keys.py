from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.db.models import ApiKey, User
from app.deps import get_current_user, get_db_session
from app.services.api_keys import issue_api_key, new_api_key_id

router = APIRouter(prefix="/auth/api-keys", tags=["auth"])


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    api_key: str
    key_prefix: str
    key_last4: str
    created_at: datetime
    expires_at: datetime | None = None


class ApiKeyListItem(BaseModel):
    id: str
    name: str
    key_prefix: str
    key_last4: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyListItem]


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    summary="Issue API key",
    responses={
        401: {"description": "Unauthorized", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def create_api_key(
    payload: CreateApiKeyRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreateResponse:
    raw_key, key_hash, key_prefix, key_last4 = issue_api_key()
    expires_at = datetime.now(UTC) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None

    row = ApiKey(
        id=new_api_key_id(),
        user_id=current_user.id,
        name=payload.name.strip(),
        key_prefix=key_prefix,
        key_last4=key_last4,
        key_hash=key_hash,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return ApiKeyCreateResponse(
        id=str(row.id),
        name=row.name,
        api_key=raw_key,
        key_prefix=row.key_prefix,
        key_last4=row.key_last4,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="List API keys",
    responses={
        401: {"description": "Unauthorized", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def list_api_keys(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ApiKeyListResponse:
    rows = db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    ).scalars().all()
    return ApiKeyListResponse(
        items=[
            ApiKeyListItem(
                id=str(row.id),
                name=row.name,
                key_prefix=row.key_prefix,
                key_last4=row.key_last4,
                created_at=row.created_at,
                revoked_at=row.revoked_at,
                last_used_at=row.last_used_at,
                expires_at=row.expires_at,
            )
            for row in rows
        ]
    )


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke API key",
    responses={
        401: {"description": "Unauthorized", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
        404: {"description": "API key not found", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    },
)
def revoke_api_key(
    api_key_id: UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    row = db.execute(select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.user_id == current_user.id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.commit()
