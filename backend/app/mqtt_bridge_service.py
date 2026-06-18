import asyncio
import logging
import time

from aiomqtt import Client, MqttError
from fastapi import WebSocket, WebSocketDisconnect

from app.models import Connection

logger = logging.getLogger(__name__)


def _decode_payload(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.hex()


MQTT_CONNECT_TIMEOUT_SECONDS = 12


async def run_mqtt_bridge_session(
    websocket: WebSocket,
    *,
    hostname: str,
    port: int,
    username: str | None,
    password: str | None,
    preset_topics: list[str],
    bridge_id: str | int,
    accept_websocket: bool = True,
) -> None:
    if accept_websocket:
        await websocket.accept()

    hostname = (hostname or "").strip()
    if not hostname:
        await websocket.send_json({"type": "status", "status": "error", "message": "未配置主机"})
        return

    port = int(port or 1883)
    client_id = f"quicknav_bridge_{bridge_id}_{int(time.time())}"
    broker_target = f"mqtt://{hostname}:{port}"

    await websocket.send_json(
        {
            "type": "status",
            "status": "connecting",
            "mode": "bridge",
            "target": broker_target,
        }
    )

    client: Client | None = None
    mqtt_task: asyncio.Task | None = None

    try:
        client = Client(
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            identifier=client_id,
            timeout=MQTT_CONNECT_TIMEOUT_SECONDS,
        )
        await asyncio.wait_for(
            client.__aenter__(),
            timeout=MQTT_CONNECT_TIMEOUT_SECONDS,
        )

        subscribed: list[str] = []
        for topic in preset_topics:
            normalized = topic.strip()
            if not normalized:
                continue
            await asyncio.wait_for(
                client.subscribe(normalized),
                timeout=MQTT_CONNECT_TIMEOUT_SECONDS,
            )
            subscribed.append(normalized)

        await websocket.send_json(
            {
                "type": "status",
                "status": "connected",
                "topics": subscribed,
                "mode": "bridge",
                "target": broker_target,
            }
        )

        async def forward_mqtt_messages() -> None:
            async for message in client.messages:
                await websocket.send_json(
                    {
                        "type": "message",
                        "topic": str(message.topic),
                        "payload": _decode_payload(message.payload),
                    }
                )

        mqtt_task = asyncio.create_task(forward_mqtt_messages())

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "subscribe":
                topic = str(data.get("topic", "")).strip()
                if topic:
                    await client.subscribe(topic)
                    await websocket.send_json({"type": "subscribed", "topic": topic})
            elif msg_type == "unsubscribe":
                topic = str(data.get("topic", "")).strip()
                if topic:
                    await client.unsubscribe(topic)
                    await websocket.send_json({"type": "unsubscribed", "topic": topic})
            elif msg_type == "publish":
                topic = str(data.get("topic", "")).strip()
                if topic:
                    payload = str(data.get("payload", ""))
                    await client.publish(topic, payload)
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        message = (
            f"连接 Broker 超时（{broker_target}）。"
            "请确认后端能访问该地址（Docker 部署时需检查容器网络）"
        )
        logger.warning("MQTT bridge timeout for %s: %s", bridge_id, broker_target)
        try:
            await websocket.send_json({"type": "status", "status": "error", "message": message})
        except Exception:
            pass
    except MqttError as exc:
        logger.warning("MQTT bridge error for %s: %s", bridge_id, exc)
        try:
            await websocket.send_json(
                {"type": "status", "status": "error", "message": str(exc)}
            )
        except Exception:
            pass
    except Exception as exc:
        logger.exception("MQTT bridge failed for %s", bridge_id)
        try:
            await websocket.send_json(
                {"type": "status", "status": "error", "message": str(exc)}
            )
        except Exception:
            pass
    finally:
        if mqtt_task:
            mqtt_task.cancel()
            try:
                await mqtt_task
            except asyncio.CancelledError:
                pass
        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass


async def run_mqtt_bridge(
    websocket: WebSocket,
    conn: Connection,
    preset_topics: list[str],
) -> None:
    await run_mqtt_bridge_session(
        websocket,
        hostname=(conn.host or "").strip(),
        port=int(conn.port or 1883),
        username=(conn.username or "").strip() or None,
        password=conn.password or None,
        preset_topics=preset_topics,
        bridge_id=conn.id,
        accept_websocket=True,
    )
