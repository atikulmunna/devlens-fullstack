"""Helpers shared by the OpenRouter clients (chat synthesis and embeddings)."""

import httpx


def describe_error(response: httpx.Response) -> str:
    """Return 'status N: <reason>' using OpenRouter's error message, so a failure says why."""
    try:
        payload = response.json()
    except ValueError:
        detail = response.text
    else:
        error = payload.get("error") if isinstance(payload, dict) else None
        detail = error.get("message") if isinstance(error, dict) else ""
    detail = (detail or "").strip()[:300]
    return f"status {response.status_code}: {detail}" if detail else f"status {response.status_code}"
