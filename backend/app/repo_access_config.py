from __future__ import annotations

from app.config import settings

_cache: dict[str, str] = {
    "gitlab_base_url": "",
    "gitlab_token": "",
    "github_token": "",
    "public_webhook_base_url": "",
}


def _fallback_gitlab_base_url() -> str:
    return settings.gitlab_base_url.strip() or "https://gitlab.com"


def apply_repo_access_cache(
    *,
    gitlab_base_url: str = "",
    gitlab_token: str = "",
    github_token: str = "",
    public_webhook_base_url: str = "",
) -> None:
    global _cache
    _cache = {
        "gitlab_base_url": gitlab_base_url.strip(),
        "gitlab_token": gitlab_token.strip(),
        "github_token": github_token.strip(),
        "public_webhook_base_url": public_webhook_base_url.strip(),
    }


def get_gitlab_base_url() -> str:
    return _cache.get("gitlab_base_url") or _fallback_gitlab_base_url()


def get_gitlab_token() -> str:
    return _cache.get("gitlab_token") or settings.gitlab_token.strip()


def get_github_token() -> str:
    return _cache.get("github_token") or settings.github_token.strip()


def get_public_webhook_base_url() -> str:
    return _cache.get("public_webhook_base_url") or settings.public_webhook_base_url.strip()


def token_hint(token: str) -> str | None:
    value = token.strip()
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"
