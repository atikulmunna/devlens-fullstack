from datetime import UTC, datetime
import secrets
from urllib.parse import quote
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.api.error_schema import ERROR_RESPONSE_SCHEMA
from app.db.models import RefreshToken, User
from app.deps import get_current_user, get_db_session
from app.services.github_oauth import (
    build_github_auth_url,
    exchange_code_for_access_token,
    fetch_github_user,
    generate_oauth_state,
    validate_oauth_state,
)
from app.services.tokens import (
    REFRESH_COOKIE_NAME,
    create_access_token,
    hash_refresh_token,
    issue_refresh_token,
    new_refresh_token_id,
    refresh_cookie_secure,
    refresh_expiry,
)

router = APIRouter(prefix="/auth", tags=["auth"])
CSRF_COOKIE_NAME = "devlens_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
REFRESH_RESPONSE_EXAMPLE = {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in_seconds": 900,
}
ME_RESPONSE_EXAMPLE = {
    "id": "d7a2ca6c-f9d1-42ce-9de0-35e0dbdc47dc",
    "github_id": 123,
    "username": "octocat",
    "email": "octo@example.com",
    "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
}

class RefreshAccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")
    expires_in_seconds: int


class CurrentUserResponse(BaseModel):
    id: str
    github_id: int
    username: str
    email: str | None = None
    avatar_url: str | None = None


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=refresh_cookie_secure(),
        samesite="lax",
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        path="/",
    )


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=refresh_cookie_secure(),
        samesite="lax",
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        path="/",
    )


def _expected_origin() -> str:
    parsed = urlparse(str(settings.frontend_url))
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _validate_origin(request: Request) -> None:
    expected = _expected_origin()
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    if origin:
        if origin.lower() != expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")
        return

    if referer:
        parsed = urlparse(referer)
        candidate = f"{parsed.scheme}://{parsed.netloc}".lower()
        if candidate != expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing request origin")


def _validate_csrf(request: Request) -> None:
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(CSRF_HEADER_NAME)
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def _persist_refresh_token(db: Session, user_id: UUID) -> str:
    token = issue_refresh_token()
    db.add(
        RefreshToken(
            id=new_refresh_token_id(),
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            expires_at=refresh_expiry(),
        )
    )
    return token


@router.get(
    "/github",
    summary="Start GitHub OAuth flow",
    description="Redirects the user to GitHub authorization page. Supports an optional frontend-relative `next` path.",
    responses={
        302: {"description": "Redirect to GitHub OAuth authorize endpoint"},
    },
)
def auth_github(next_path: str = Query(default="/profile", alias="next")) -> RedirectResponse:
    state = generate_oauth_state(next_path=next_path)
    auth_url = build_github_auth_url(state)
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/callback",
    summary="Handle GitHub OAuth callback",
    description="Exchanges OAuth code, upserts user, sets refresh+CSRF cookies, then redirects back to frontend.",
    responses={
        302: {"description": "Login succeeded and redirected to frontend"},
        400: {
            "description": "Invalid OAuth state or request",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        502: {
            "description": "GitHub payload was invalid",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def auth_callback(code: str, state: str, db: Session = Depends(get_db_session)) -> RedirectResponse:
    state_data = validate_oauth_state(state)

    access_token = exchange_code_for_access_token(code)
    github_user = fetch_github_user(access_token)

    github_id = github_user.get("id")
    login = github_user.get("login")
    if github_id is None or not login:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid GitHub profile payload")

    existing = db.execute(select(User).where(User.github_id == int(github_id))).scalar_one_or_none()

    if existing:
        existing.username = login
        existing.email = github_user.get("email")
        existing.avatar_url = github_user.get("avatar_url")
        user = existing
    else:
        user = User(
            id=uuid4(),
            github_id=int(github_id),
            username=login,
            email=github_user.get("email"),
            avatar_url=github_user.get("avatar_url"),
        )
        db.add(user)

    db.flush()
    refresh_token = _persist_refresh_token(db, user.id)
    db.commit()

    redirect_path = state_data.get("next") or "/profile"
    safe_redirect = redirect_path if str(redirect_path).startswith("/") else "/profile"
    redirect_url = f"{str(settings.frontend_url).rstrip('/')}{quote(safe_redirect, safe='/:?=&')}"
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    _set_refresh_cookie(response, refresh_token)
    _set_csrf_cookie(response, secrets.token_urlsafe(24))
    return response


@router.post(
    "/refresh",
    response_model=RefreshAccessTokenResponse,
    summary="Rotate refresh cookie and issue a new access token",
    description=(
        "Requires matching CSRF cookie/header and valid origin. "
        "On success, revokes old refresh token, sets a new cookie pair, and returns bearer access token."
    ),
    responses={
        200: {"content": {"application/json": {"example": REFRESH_RESPONSE_EXAMPLE}}},
        401: {
            "description": "Missing, invalid, revoked, or expired refresh token",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
        403: {
            "description": "Origin or CSRF validation failed",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def refresh_access_token(request: Request, db: Session = Depends(get_db_session)) -> JSONResponse:
    _validate_origin(request)
    _validate_csrf(request)

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    token_hash = hash_refresh_token(refresh_token)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if not token_row or token_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if token_row.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.execute(select(User).where(User.id == token_row.user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    token_row.revoked_at = datetime.now(UTC)
    rotated_token = _persist_refresh_token(db, user.id)
    access_token = create_access_token(user.id)
    db.commit()

    response = JSONResponse(
        {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in_seconds": settings.jwt_access_ttl_minutes * 60,
        }
    )
    _set_refresh_cookie(response, rotated_token)
    _set_csrf_cookie(response, secrets.token_urlsafe(24))
    return response


@router.delete(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke refresh token",
    description="Revokes current refresh token when present and clears refresh/CSRF cookies.",
    responses={
        403: {
            "description": "Origin or CSRF validation failed",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def logout(request: Request, db: Session = Depends(get_db_session)) -> Response:
    _validate_origin(request)
    _validate_csrf(request)

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        token_hash = hash_refresh_token(refresh_token)
        token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
        if token_row and token_row.revoked_at is None:
            token_row.revoked_at = datetime.now(UTC)
            db.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Fetch current authenticated user",
    responses={
        200: {"content": {"application/json": {"example": ME_RESPONSE_EXAMPLE}}},
        401: {
            "description": "Missing or invalid bearer token",
            "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}},
        },
    },
)
def current_user_me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return {
        "id": str(current_user.id),
        "github_id": current_user.github_id,
        "username": current_user.username,
        "email": current_user.email,
        "avatar_url": current_user.avatar_url,
    }
