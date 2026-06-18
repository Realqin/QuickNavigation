import re

from app.config import settings

LOCAL_HOST_ALIASES = {"localhost", "127.0.0.1", "0.0.0.0"}
DEFAULT_KAFKA_PORT = 9092
_BROKER_PART_RE = re.compile(r"^([^:\s]+)(?::(\d+))?$")


def resolve_kafka_broker_host(host: str) -> str:
    normalized = host.strip().lower()
    if normalized in LOCAL_HOST_ALIASES:
        return settings.redpanda_kafka_host
    return host.strip()


def parse_kafka_brokers(host: str | None, port: int | None = None) -> list[str]:
    text = str(host or "").strip()
    if not text:
        return []

    if "," not in text and ":" not in text and port:
        return [f"{resolve_kafka_broker_host(text)}:{int(port)}"]

    brokers: list[str] = []
    for raw in re.split(r"[,;\n]+", text):
        part = raw.strip()
        if not part:
            continue
        matched = _BROKER_PART_RE.match(part)
        if not matched:
            continue
        broker_host = resolve_kafka_broker_host(matched.group(1))
        broker_port = int(matched.group(2) or port or DEFAULT_KAFKA_PORT)
        brokers.append(f"{broker_host}:{broker_port}")
    return brokers


def format_kafka_brokers(host: str | None, port: int | None = None) -> str:
    return ",".join(parse_kafka_brokers(host, port))


def normalize_kafka_brokers_field(host: str | None, port: int | None = None) -> tuple[str, list[str]]:
    brokers = parse_kafka_brokers(host, port)
    if not brokers:
        return "", []
    return ",".join(brokers), brokers


def validate_kafka_brokers(host: str | None, port: int | None = None) -> list[str]:
    text = str(host or "").strip()
    if not text:
        raise ValueError("请输入 Kafka 集群地址")

    brokers = parse_kafka_brokers(host, port)
    if not brokers:
        raise ValueError("Kafka 集群地址格式无效，示例：10.0.0.1:9092,10.0.0.2:9092")

    if len(text) > 512:
        raise ValueError("Kafka 集群地址过长")

    return brokers
