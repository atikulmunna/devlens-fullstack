import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.config import settings


GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
STATE_TTL_SECONDS = 600


def _sign_payload(payload: str) -> str:
    return hmac.new(settings.jwt_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_oauth_state(next_path: str | None = None) -> str:
    body = {
        "iat": int(time.time()),
        "next": next_path or "/profile",
    }
    payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8")).decode("utf-8").rstrip("=")
    signature = _sign_payload(payload)
    return f"{payload}.{signature}"


def validate_oauth_state(state: str) -> dict:
    try:
        payload, signature = state.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc

    expected = _sign_payload(payload)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state signature")

    try:
        padded = payload + ("=" * (-len(payload) % 4))
        data = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state payload") from exc

    issued_at = int(data.get("iat", 0))
    if int(time.time()) - issued_at > STATE_TTL_SECONDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state expired")

    return data


def build_github_auth_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": str(settings.github_oauth_redirect_uri),
            "scope": "read:user user:email",
            "state": state,
        }
    )
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


def exchange_code_for_access_token(code: str) -> str:
    payload = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": str(settings.github_oauth_redirect_uri),
    }

    headers = {"Accept": "application/json"}
    with httpx.Client(timeout=10.0) as client:
        response = client.post(GITHUB_ACCESS_TOKEN_URL, data=payload, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to exchange OAuth code")

    data = response.json()
    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub access token missing")

    return token


def fetch_github_user(access_token: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=10.0) as client:
        user_response = client.get(GITHUB_USER_URL, headers=headers)

    if user_response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch GitHub profile")

    user = user_response.json()

    if not user.get("email"):
        with httpx.Client(timeout=10.0) as client:
            emails_response = client.get(GITHUB_EMAILS_URL, headers=headers)
        if emails_response.status_code == 200:
            for email in emails_response.json():
                if email.get("primary") and email.get("verified"):
                    user["email"] = email.get("email")
                    break

    return user
