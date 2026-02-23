from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, status

from app.config import settings

SHARE_TOKEN_AUDIENCE = "devlens-share"


def share_token_expiry(ttl_days: int | None = None) -> datetime:
    ttl = ttl_days if ttl_days is not None else settings.share_token_ttl_days
    if ttl <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ttl_days must be greater than 0")
    if ttl > 30:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ttl_days must be <= 30")
    return datetime.now(UTC) + timedelta(days=ttl)


def new_share_token_id() -> UUID:
    return uuid4()


def create_share_token(repo_id: UUID, share_id: UUID, expires_at: datetime) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(repo_id),
        "aud": SHARE_TOKEN_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(share_id),
        "typ": "share",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_share_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=SHARE_TOKEN_AUDIENCE)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Share token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid share token") from exc

    if payload.get("typ") != "share":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid share token type")
    if not payload.get("sub") or not payload.get("jti"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid share token payload")
    return payload
