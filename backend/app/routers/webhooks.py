import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import Subscription
from app.repo_service import (
    gitlab_repo_path,
    push_branch,
    repos_match,
    schedule_log_diff,
    short_sha,
    subscription_branch,
    subscription_provider,
    subscription_repo_candidates,
)
from app.schemas import ActivityLogOut, DatabaseWebhookPayload
from app.services import (
    build_gitlab_subscription_links,
    create_activity_log,
    handle_database_webhook,
    match_gitlab_link,
    refresh_subscription_from_connection,
    _primary_project_environment,
)
from app.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_github_signature(body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def _verify_gitlab_token(token: str | None) -> bool:
    secret = settings.gitlab_webhook_secret.strip()
    if not secret or secret == "change-me-gitlab-secret":
        return True
    return bool(token and token == secret)


async def _broadcast_log(log: Any) -> None:
    data = ActivityLogOut.model_validate(log).model_dump(mode="json")
    await ws_manager.broadcast({"type": "log:new", "data": data})


def _match_subscription(
    sub: Subscription,
    repo_full_name: str | None,
    branch: str,
    event: str,
    provider: str,
) -> bool:
    if not sub.enabled:
        return False
    sub_provider = subscription_provider(sub)
    if sub_provider and sub_provider != provider:
        return False
    repo_candidates = subscription_repo_candidates(sub)
    if not repo_candidates or not repo_full_name:
        return False
    if not any(repos_match(candidate, repo_full_name) for candidate in repo_candidates):
        return False
    if sub.github_events and event not in sub.github_events:
        return False
    expected_branch = subscription_branch(sub)
    if expected_branch and expected_branch != branch:
        return False
    return True


def _is_zero_sha(sha: str | None) -> bool:
    if not sha:
        return True
    return sha.strip("0") == ""


def _normalize_commits(commits: list[dict[str, Any]], fallback_sha: str | None = None) -> list[dict[str, Any]]:
    if commits:
        return commits
    if fallback_sha and not _is_zero_sha(fallback_sha):
        return [{"id": fallback_sha, "message": "Push event", "author": {"name": None}}]
    return []


def _commit_timestamp(commit: dict[str, Any]) -> str | None:
    for key in ("timestamp", "committed_date", "authored_date", "created_at"):
        ts = commit.get(key)
        if isinstance(ts, str) and ts.strip():
            return ts.strip()
    return None


async def _handle_push_event(
    db: Session,
    *,
    provider: str,
    repo_full_name: str,
    branch: str,
    commits: list[dict[str, Any]],
    source_type: str,
) -> list[Any]:
    logs: list[Any] = []
    subs = (
        db.query(Subscription)
        .options(joinedload(Subscription.connection))
        .all()
    )
    for sub in subs:
        refresh_subscription_from_connection(db, sub)
        conn = sub.connection
        if not conn:
            continue

        if provider == "gitlab":
            matched = any(
                match_gitlab_link(link, repo_full_name, branch)
                for link in build_gitlab_subscription_links(conn, sub.link_enabled)
            )
            if not matched:
                continue
        elif not _match_subscription(sub, repo_full_name, branch, "push", provider):
            continue

        project, environment = _primary_project_environment(db, conn)
        for commit in commits:
            if commit.get("distinct") is False:
                continue
            sha = commit.get("id")
            if not sha or _is_zero_sha(sha):
                continue
            message = (commit.get("message") or "Push commit").split("\n")[0]
            author_info = commit.get("author") or {}
            author = author_info.get("name") if isinstance(author_info, dict) else None
            if not author:
                author = commit.get("author_name")
            log = create_activity_log(
                db,
                subscription_id=sub.id,
                connection_id=conn.id,
                project=project,
                environment=environment,
                source_type=source_type,
                title=f"Push · {branch} · {short_sha(sha)}",
                summary=message,
                payload={
                    "event": "push",
                    "provider": provider,
                    "repo": repo_full_name,
                    "branch": branch,
                    "commit_sha": sha,
                    "committed_at": _commit_timestamp(commit),
                    "commit_url": commit.get("url"),
                    "files": {
                        "added": commit.get("added") or [],
                        "removed": commit.get("removed") or [],
                        "modified": commit.get("modified") or [],
                    },
                    "diff": "",
                },
                author=author,
            )
            logs.append(log)
            schedule_log_diff(log.id, provider, repo_full_name, sha)

    if not logs:
        logger.warning(
            "Push ignored: no matching subscription for provider=%s repo=%s branch=%s commits=%s",
            provider,
            repo_full_name,
            branch,
            len(commits),
        )

    for log in logs:
        asyncio.create_task(_broadcast_log(log))
    return logs


def _push_response(logs: list[Any], *, provider: str, repo: str, branch: str, commits: int) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ok": True,
        "log_ids": [log.id for log in logs],
        "count": len(logs),
        "repo": repo,
        "branch": branch,
        "commits": commits,
    }
    if not logs:
        body["hint"] = (
            "未写入活动日志：请确认已在「日志订阅」创建并启用订阅，"
            "且连接的 GitLab 地址与推送仓库、分支一致（订阅表中的「仓库」「分支」列）。"
        )
    return body


@router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event = request.headers.get("X-GitHub-Event", "unknown")

    if settings.github_webhook_secret != "change-me-github-secret":
        if not _verify_github_signature(body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    repo_full_name = payload.get("repository", {}).get("full_name")

    if event == "push" and repo_full_name:
        branch = push_branch(payload)
        commits = _normalize_commits(payload.get("commits") or [], payload.get("after"))
        logs = await _handle_push_event(
            db,
            provider="github",
            repo_full_name=repo_full_name,
            branch=branch,
            commits=commits,
            source_type="github",
        )
        return _push_response(logs, provider="github", repo=repo_full_name, branch=branch, commits=len(commits))

    return {"ok": True, "message": "Event ignored"}


@router.post("/gitlab")
async def gitlab_webhook(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("X-Gitlab-Token")
    if not _verify_gitlab_token(token):
        raise HTTPException(status_code=401, detail="Invalid GitLab token")

    payload = json.loads(await request.body())
    object_kind = payload.get("object_kind")
    if object_kind != "push":
        return {"ok": True, "message": f"Event ignored: {object_kind}"}

    repo_full_name = gitlab_repo_path(payload)
    if not repo_full_name:
        return {"ok": True, "message": "Missing project path"}

    branch = push_branch(payload)
    commits = _normalize_commits(payload.get("commits") or [], payload.get("after"))
    logs = await _handle_push_event(
        db,
        provider="gitlab",
        repo_full_name=repo_full_name,
        branch=branch,
        commits=commits,
        source_type="gitlab",
    )
    return _push_response(logs, provider="gitlab", repo=repo_full_name, branch=branch, commits=len(commits))


@router.post("/database")
async def database_webhook(
    payload: DatabaseWebhookPayload,
    secret: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if secret:
        payload.webhook_secret = secret
    try:
        log = handle_database_webhook(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _broadcast_log(log)
    return {"ok": True, "log_id": log.id}
