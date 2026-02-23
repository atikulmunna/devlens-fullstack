from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

GITHUB_API_BASE = "https://api.github.com"


def normalize_github_repo_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GitHub URL") from exc

    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only github.com repository URLs are supported")

    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub URL must be in /owner/repo format")

    owner = path_parts[0]
    repo = path_parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GitHub repository path")

    return f"https://github.com/{owner}/{repo}"


def resolve_public_repo_snapshot(github_url: str) -> dict:
    normalized = normalize_github_repo_url(github_url)
    owner_repo = normalized.removeprefix("https://github.com/")

    repo_api = f"{GITHUB_API_BASE}/repos/{owner_repo}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=10.0) as client:
        repo_response = client.get(repo_api, headers=headers)

        if repo_response.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if repo_response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch repository metadata")

        repo_data = repo_response.json()
        default_branch = repo_data.get("default_branch") or "main"

        commit_response = client.get(f"{repo_api}/commits/{default_branch}", headers=headers)
        if commit_response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to resolve repository head commit")

        commit_sha = commit_response.json().get("sha")
        if not commit_sha:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Repository head commit SHA missing")

    return {
        "github_url": normalized,
        "full_name": repo_data.get("full_name"),
        "owner": repo_data.get("owner", {}).get("login") or owner_repo.split("/")[0],
        "name": repo_data.get("name") or owner_repo.split("/")[1],
        "description": repo_data.get("description"),
        "stars": repo_data.get("stargazers_count"),
        "forks": repo_data.get("forks_count"),
        "language": repo_data.get("language"),
        "size_kb": repo_data.get("size"),
        "default_branch": default_branch,
        "commit_sha": commit_sha,
    }
