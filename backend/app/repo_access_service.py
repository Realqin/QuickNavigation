from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import RepoAccessSettings
from app.repo_access_config import (
    apply_repo_access_cache,
    get_github_token,
    get_gitlab_base_url,
    get_gitlab_token,
    get_public_webhook_base_url,
    token_hint,
)
from app.schemas import RepoAccessSettingsOut, RepoAccessSettingsUpdate


def _get_or_create_row(db: Session) -> RepoAccessSettings:
    row = db.query(RepoAccessSettings).filter(RepoAccessSettings.id == 1).first()
    if row:
        return row
    row = RepoAccessSettings(
        id=1,
        gitlab_base_url=settings.gitlab_base_url.strip(),
        gitlab_token=settings.gitlab_token.strip(),
        gitlab_ssh_private_key="",
        github_token=settings.github_token.strip(),
        public_webhook_base_url=settings.public_webhook_base_url.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def sync_repo_access_cache_from_db(db: Session) -> None:
    row = _get_or_create_row(db)
    apply_repo_access_cache(
        gitlab_base_url=row.gitlab_base_url,
        gitlab_token=row.gitlab_token,
        gitlab_ssh_private_key=row.gitlab_ssh_private_key or "",
        github_token=row.github_token,
        public_webhook_base_url=row.public_webhook_base_url,
    )


def get_repo_access_settings_out(db: Session) -> RepoAccessSettingsOut:
    row = _get_or_create_row(db)
    gitlab_token = get_gitlab_token()
    github_token = get_github_token()
    return RepoAccessSettingsOut(
        gitlab_base_url=get_gitlab_base_url(),
        gitlab_token_set=bool(gitlab_token),
        gitlab_token_hint=token_hint(gitlab_token),
        gitlab_ssh_key_set=bool((row.gitlab_ssh_private_key or "").strip()),
        github_token_set=bool(github_token),
        github_token_hint=token_hint(github_token),
        public_webhook_base_url=get_public_webhook_base_url(),
        updated_at=row.updated_at,
    )


def update_repo_access_settings(db: Session, data: RepoAccessSettingsUpdate) -> RepoAccessSettingsOut:
    row = _get_or_create_row(db)
    payload = data.model_dump(exclude_unset=True)
    if "gitlab_base_url" in payload and payload["gitlab_base_url"] is not None:
        row.gitlab_base_url = payload["gitlab_base_url"].strip()
    if "gitlab_token" in payload and payload["gitlab_token"] is not None:
        row.gitlab_token = payload["gitlab_token"].strip()
    if "gitlab_ssh_private_key" in payload and payload["gitlab_ssh_private_key"] is not None:
        row.gitlab_ssh_private_key = payload["gitlab_ssh_private_key"].strip()
    if "github_token" in payload and payload["github_token"] is not None:
        row.github_token = payload["github_token"].strip()
    if "public_webhook_base_url" in payload and payload["public_webhook_base_url"] is not None:
        row.public_webhook_base_url = payload["public_webhook_base_url"].strip()
    db.commit()
    db.refresh(row)
    sync_repo_access_cache_from_db(db)
    return get_repo_access_settings_out(db)
