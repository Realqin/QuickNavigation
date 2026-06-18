import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

GITHUB_HOSTS = {"github.com", "www.github.com"}


def parse_github_url(url: str) -> tuple[str | None, str | None]:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None, None
    if parsed.netloc.lower() not in GITHUB_HOSTS:
        return None, None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None, None
    repo = f"{parts[0]}/{parts[1]}"
    branch = None
    if len(parts) >= 4 and parts[2] == "tree":
        branch = parts[3]
    elif len(parts) >= 4 and parts[2] == "blob":
        branch = parts[3]
    return repo, branch


def subscription_repo(sub) -> str | None:
    if sub.github_repo:
        return sub.github_repo
    if sub.connection:
        repo, _ = parse_github_url(sub.connection.url)
        return repo
    return None


def subscription_branch(sub) -> str | None:
    if sub.github_branch:
        return sub.github_branch
    if sub.connection:
        _, branch = parse_github_url(sub.connection.url)
        return branch
    return None


def push_branch(payload: dict[str, Any]) -> str:
    ref = payload.get("ref") or ""
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/") :]
    return ref.split("/")[-1] if ref else "unknown"


async def fetch_commit_diff(repo: str, sha: str) -> str:
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "QuickNavigation/1.0",
    }
    token = settings.github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repo}/commits/{sha}"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                return ""
    except httpx.HTTPError:
        return ""
    return ""


def short_sha(sha: str | None) -> str:
    if not sha:
        return ""
    return sha[:7] if len(sha) >= 7 else sha


def extract_commit_sha(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    sha = payload.get("commit_sha")
    if isinstance(sha, str) and sha:
        return sha
    return None
