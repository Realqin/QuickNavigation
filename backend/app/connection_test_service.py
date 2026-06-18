import socket
import time

from sqlalchemy.orm import Session

from app.schema_monitor_service import ping_schema_monitor_connection
from app.schemas import ConnectionTestOut, ConnectionTestRequest
from app.services import get_label_kind


def test_connection(db: Session, data: ConnectionTestRequest) -> ConnectionTestOut:
    kind = get_label_kind(db, data.type)
    host = data.host.strip()
    port = int(data.port) if data.port is not None else None
    username = (data.username or "").strip()
    password = (data.password or "").strip()

    if kind == "database":
        if not username:
            return ConnectionTestOut(ok=False, message="请填写用户名")
        if not password:
            return ConnectionTestOut(ok=False, message="请填写密码")
        return ping_schema_monitor_connection(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    if kind == "terminal":
        return _test_tcp_connection(host, port, label="终端")

    if kind == "redis":
        return _test_tcp_connection(host, port, label="Redis")

    if kind == "mqtt":
        return _test_tcp_connection(host, port, label="MQTT")

    if kind == "kafka":
        from app.kafka_broker_utils import parse_kafka_brokers

        brokers = parse_kafka_brokers(host, port if port else None)
        if not brokers:
            return ConnectionTestOut(ok=False, message="Kafka 集群地址格式无效")
        return _test_kafka_brokers(brokers)

    return ConnectionTestOut(
        ok=False,
        message="仅支持数据库、终端模拟器、Redis、MQTT、Kafka 类型测试连接",
    )


def _test_kafka_brokers(brokers: list[str]) -> ConnectionTestOut:
    results: list[str] = []
    ok_count = 0
    total_latency = 0.0
    for endpoint in brokers:
        host, _, port_text = endpoint.rpartition(":")
        try:
            port = int(port_text)
        except ValueError:
            results.append(f"{endpoint} 端口无效")
            continue
        result = _test_tcp_connection(host, port, label="Kafka")
        if result.ok:
            ok_count += 1
            total_latency += result.latency_ms or 0
            results.append(f"{endpoint} 连通")
        else:
            results.append(f"{endpoint} 失败")
    if ok_count == len(brokers):
        avg_latency = round(total_latency / ok_count, 1) if ok_count else None
        return ConnectionTestOut(
            ok=True,
            message=f"Kafka 集群 {ok_count}/{len(brokers)} 节点连通",
            latency_ms=avg_latency,
        )
    if ok_count > 0:
        return ConnectionTestOut(
            ok=False,
            message=f"Kafka 集群部分节点不可达（{ok_count}/{len(brokers)}）：{'；'.join(results)}",
        )
    return ConnectionTestOut(ok=False, message=f"Kafka 集群不可达：{'；'.join(results)}")


def _test_tcp_connection(host: str, port: int, *, label: str) -> ConnectionTestOut:
    started = time.perf_counter()
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection((host, port), timeout=10)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return ConnectionTestOut(
            ok=True,
            message=f"{label} 端口连通（{host}:{port}）",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return ConnectionTestOut(ok=False, message=f"连接失败：{exc}")
    finally:
        if sock is not None:
            sock.close()
