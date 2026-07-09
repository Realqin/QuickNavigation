import base64
from urllib.parse import quote, urlparse

from fastapi import HTTPException

from app.config import settings
from app.models import Connection

LOCAL_HOST_ALIASES = {"localhost", "127.0.0.1", "0.0.0.0"}


def resolve_sshwifty_scheme(request_host: str | None = None) -> str:
    configured = settings.sshwifty_public_scheme.strip().lower()
    if configured in {"http", "https"}:
        return configured
    hostname = (request_host or "").split(":")[0].strip().lower()
    if hostname in LOCAL_HOST_ALIASES:
        return "http"
    return "https"


def resolve_terminal_host(host: str | None) -> str:
    normalized = (host or "").strip().lower()
    if normalized in LOCAL_HOST_ALIASES:
        return settings.sshwifty_ssh_host
    return (host or "").strip()


def build_sshwifty_public_base(request_host: str | None = None) -> str:
    scheme = resolve_sshwifty_scheme(request_host)
    if request_host:
        hostname = request_host.split(":")[0].strip()
        if hostname:
            return f"{scheme}://{hostname}:{settings.sshwifty_public_port}"
    configured = settings.public_webhook_base_url.strip()
    if configured:
        parsed = urlparse(configured)
        if parsed.hostname and parsed.hostname not in LOCAL_HOST_ALIASES:
            return f"{scheme}://{parsed.hostname}:{settings.sshwifty_public_port}"
    return f"{scheme}://localhost:{settings.sshwifty_public_port}"


def _encode_launch_password(password: str) -> str:
    return base64.urlsafe_b64encode(password.encode()).decode().rstrip("=")


def build_sshwifty_launch_url(conn: Connection, *, public_base: str) -> str:
    host = resolve_terminal_host(conn.host)
    if not host:
        raise HTTPException(status_code=400, detail="终端连接未配置主机")

    username = (conn.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="终端连接未配置账号")

    password = (conn.password or "").strip()
    if not password:
        raise HTTPException(status_code=400, detail="终端连接未保存密码，无法自动登录")

    port = int(conn.port or 22)
    launcher = f"{username}@{host}:{port}|Password|utf-8"
    encoded_launcher = quote(launcher, safe="@:|-")
    encoded_password = quote(_encode_launch_password(password), safe="")
    return (
        f"{public_base.rstrip('/')}/?qn_pwd={encoded_password}#+SSH:{encoded_launcher}"
    )


def prepare_sshwifty_open(conn: Connection, *, public_base: str) -> dict:
    return {
        "embed_url": build_sshwifty_launch_url(conn, public_base=public_base),
        "connection_name": conn.name,
    }
