from __future__ import annotations

from pathlib import Path

from app.config import settings

_cache: dict[str, str] = {
    "gitlab_base_url": "",
    "gitlab_token": "",
    "github_token": "",
    "public_webhook_base_url": "",
}

_gitlab_ssh_key_path: str | None = None


def _fallback_gitlab_base_url() -> str:
    return settings.gitlab_base_url.strip() or "https://gitlab.com"


def _gitlab_ssh_key_file() -> Path:
    return Path(settings.api_repo_cache_dir) / ".gitlab_deploy_key"


def sync_gitlab_ssh_key_file(private_key: str) -> None:
    global _gitlab_ssh_key_path
    path = _gitlab_ssh_key_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (private_key or "").strip()
    if not text:
        _gitlab_ssh_key_path = None
        if path.exists():
            path.unlink(missing_ok=True)
        return
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    _gitlab_ssh_key_path = str(path)


def get_gitlab_ssh_command() -> str | None:
    path = _gitlab_ssh_key_path or (
        str(_gitlab_ssh_key_file()) if _gitlab_ssh_key_file().exists() else None
    )
    if not path or not Path(path).exists():
        return None
    return f'ssh -i "{path}" -o StrictHostKeyChecking=no -o IdentitiesOnly=yes'


def apply_repo_access_cache(
    *,
    gitlab_base_url: str = "",
    gitlab_token: str = "",
    gitlab_ssh_private_key: str | None = None,
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
    if gitlab_ssh_private_key is not None:
        sync_gitlab_ssh_key_file(gitlab_ssh_private_key)


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
