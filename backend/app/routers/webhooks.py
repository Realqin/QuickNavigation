import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Connection, Subscription
from app.schemas import ActivityLogOut, DatabaseWebhookPayload
from app.services import create_activity_log, handle_database_webhook, _primary_project_environment
from app.websocket_manager import ws_manager

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


async def _broadcast_log(log: Any) -> None:
    data = ActivityLogOut.model_validate(log).model_dump(mode="json")
    await ws_manager.broadcast({"type": "log:new", "data": data})


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

    subs = (
        db.query(Subscription)
        .filter(
            Subscription.enabled.is_(True),
            Subscription.github_repo.isnot(None),
            Subscription.github_repo != "",
        )
        .all()
    )

    matched = None
    for sub in subs:
        if sub.github_repo and repo_full_name and sub.github_repo == repo_full_name:
            if sub.github_events and event not in sub.github_events:
                continue
            matched = sub
            break

    if not matched:
        return {"ok": True, "message": "No matching subscription"}

    conn = matched.connection
    title, summary, author = _parse_github_event(event, payload)
    project, environment = _primary_project_environment(db, conn)

    log = create_activity_log(
        db,
        subscription_id=matched.id,
        connection_id=conn.id,
        project=project,
        environment=environment,
        source_type="github",
        title=title,
        summary=summary,
        payload={"event": event, "repo": repo_full_name},
        author=author,
    )
    await _broadcast_log(log)
    return {"ok": True, "log_id": log.id}


def _parse_github_event(event: str, payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    if event == "push":
        ref = payload.get("ref", "")
        branch = ref.split("/")[-1] if ref else "unknown"
        commits = payload.get("commits", [])
        if commits:
            last = commits[-1]
            msg = last.get("message", "push event")
            author = last.get("author", {}).get("name")
            return f"Push to {branch}", msg.split("\n")[0], author
        pusher = payload.get("pusher", {}).get("name")
        return f"Push to {branch}", None, pusher

    if event == "pull_request":
        action = payload.get("action", "updated")
        pr = payload.get("pull_request", {})
        title = pr.get("title", "Pull Request")
        user = pr.get("user", {}).get("login")
        return f"PR {action}: {title}", pr.get("body", "")[:200] if pr.get("body") else None, user

    if event == "release":
        release = payload.get("release", {})
        tag = release.get("tag_name", "release")
        author = release.get("author", {}).get("login")
        return f"Release {tag}", release.get("name"), author

    sender = payload.get("sender", {}).get("login")
    return f"GitHub {event}", None, sender


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
