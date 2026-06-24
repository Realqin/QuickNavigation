import asyncio
import json
import logging
import ssl
from typing import Any
from urllib.parse import quote, urlencode

import websockets
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from app.k8s_monitor_service import (
    _get_kubesphere_auth_headers,
    _uses_kubesphere_password_auth,
)
from app.models import K8sClusterConfig

logger = logging.getLogger(__name__)

K8S_CHANNEL_STDIN = 0
K8S_CHANNEL_STDOUT = 1
K8S_CHANNEL_STDERR = 2
K8S_CHANNEL_ERROR = 3
K8S_CHANNEL_RESIZE = 4
K8S_EXEC_SUBPROTOCOL = "v4.channel.k8s.io"


def _build_k8s_auth_headers(cluster: K8sClusterConfig) -> dict[str, str]:
    headers = {"Accept": "*/*"}
    if _uses_kubesphere_password_auth(cluster):
        headers.update(_get_kubesphere_auth_headers(cluster))
    elif (cluster.auth_type or "password") == "token":
        token = str(cluster.password or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail="Token 未配置")
        headers["Authorization"] = f"Bearer {token}"
    else:
        import base64

        username = str(cluster.username or "").strip()
        password = str(cluster.password or "").strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="账号或密码未配置")
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    return headers


def _build_exec_ws_url(
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    pod_name: str,
    container: str | None = None,
) -> str:
    base = cluster.api_server.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    params: list[tuple[str, str]] = [
        ("stdin", "true"),
        ("stdout", "true"),
        ("stderr", "true"),
        ("tty", "true"),
        ("command", "/bin/sh"),
    ]
    if container:
        params.append(("container", container))
    query = urlencode(params, quote_via=quote)
    return (
        f"{ws_base}/api/v1/namespaces/{quote(namespace, safe='')}/pods/{quote(pod_name, safe='')}/exec?{query}"
    )


def _build_ssl_context(cluster: K8sClusterConfig) -> ssl.SSLContext | None:
    if cluster.api_server.startswith("https://"):
        context = ssl.create_default_context()
        if not cluster.verify_ssl:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context
    return None


def _encode_channel(channel: int, payload: bytes) -> bytes:
    return bytes([channel]) + payload


async def _send_status(websocket: WebSocket, status: str, message: str = "") -> None:
    payload: dict[str, Any] = {"type": "status", "status": status}
    if message:
        payload["message"] = message
    await websocket.send_json(payload)


async def _forward_k8s_to_client(k8s_ws: Any, client_ws: WebSocket) -> None:
    async for message in k8s_ws:
        if isinstance(message, str):
            message = message.encode("utf-8")
        if not message:
            continue
        channel = message[0]
        payload = message[1:]
        if channel in {K8S_CHANNEL_STDOUT, K8S_CHANNEL_STDERR}:
            text = payload.decode("utf-8", errors="replace")
            if text:
                await client_ws.send_json({"type": "output", "data": text})
        elif channel == K8S_CHANNEL_ERROR:
            text = payload.decode("utf-8", errors="replace").strip()
            if text:
                await client_ws.send_json({"type": "error", "message": text})


async def _forward_client_to_k8s(client_ws: WebSocket, k8s_ws: Any) -> None:
    while True:
        message = await client_ws.receive_json()
        message_type = str(message.get("type") or "").strip().lower()
        if message_type == "input":
            data = str(message.get("data") or "")
            await k8s_ws.send(_encode_channel(K8S_CHANNEL_STDIN, data.encode("utf-8")))
            continue
        if message_type == "resize":
            cols = int(message.get("cols") or 80)
            rows = int(message.get("rows") or 24)
            resize_payload = json.dumps({"Width": cols, "Height": rows}).encode("utf-8")
            await k8s_ws.send(_encode_channel(K8S_CHANNEL_RESIZE, resize_payload))


async def run_k8s_exec_bridge(
    websocket: WebSocket,
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    pod_name: str,
    container: str | None = None,
) -> None:
    namespace = namespace.strip()
    pod_name = pod_name.strip()
    container = (container or "").strip() or None
    if not namespace or not pod_name:
        await _send_status(websocket, "error", "namespace 与 pod_name 不能为空")
        await websocket.close(code=4400)
        return

    ws_url = _build_exec_ws_url(
        cluster,
        namespace=namespace,
        pod_name=pod_name,
        container=container,
    )
    headers = _build_k8s_auth_headers(cluster)
    ssl_context = _build_ssl_context(cluster)

    try:
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            subprotocols=[K8S_EXEC_SUBPROTOCOL],
            ssl=ssl_context,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
        ) as k8s_ws:
            await _send_status(websocket, "connected")
            forward_tasks = [
                asyncio.create_task(_forward_k8s_to_client(k8s_ws, websocket)),
                asyncio.create_task(_forward_client_to_k8s(websocket, k8s_ws)),
            ]
            done, pending = await asyncio.wait(
                forward_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                try:
                    await task
                except (WebSocketDisconnect, ConnectionClosed, asyncio.CancelledError):
                    pass
                except Exception as exc:
                    logger.warning("k8s exec bridge task failed: %s", exc)
    except HTTPException as exc:
        await _send_status(websocket, "error", str(exc.detail))
        await websocket.close(code=4400)
    except Exception as exc:
        logger.exception("k8s exec bridge failed")
        await _send_status(websocket, "error", f"连接容器终端失败：{exc}")
        await websocket.close(code=1011)
