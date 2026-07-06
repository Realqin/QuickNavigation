from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DictItemBase(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    sort_order: int = 0

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        allowed = {"project", "environment", "label", "connection_group"}
        if value not in allowed:
            raise ValueError(f"type 必须是 {', '.join(sorted(allowed))}")
        return value


class DictItemCreate(DictItemBase):
    pass


class DictItemUpdate(BaseModel):
    type: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    sort_order: int | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed = {"project", "environment", "label", "connection_group"}
        if value not in allowed:
            raise ValueError(f"type 必须是 {', '.join(sorted(allowed))}")
        return value


class DictItemOut(BaseModel):
    id: int
    type: str
    name: str
    description: str | None
    sort_order: int
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_item(cls, item: Any) -> "DictItemOut":
        return cls(
            id=item.id,
            type=item.dict_type,
            name=item.name,
            description=item.description,
            sort_order=item.sort_order,
            is_system=bool(getattr(item, "is_system", False)),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


def _optional_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "none", "null"}:
        return ""
    return text


class SubLinkItem(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=512)
    clone_url: str | None = Field(default=None, max_length=512)
    is_reachable: bool | None = None
    last_checked_at: datetime | str | None = None


class MqttSubscriptionItem(BaseModel):
    topic: str = Field(min_length=1, max_length=256)
    name: str | None = Field(default=None, max_length=128)


class ConnectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(default="", max_length=512)
    description: str | None = None
    projects: list[int] = Field(default_factory=list)
    environments: list[int] = Field(default_factory=list)
    type: int = Field(default=1)
    group_id: int | None = None
    is_shared: bool = False
    sort_order: int = 0
    icon: str | None = None
    sub_links: list[SubLinkItem] = Field(default_factory=list)
    host: str | None = Field(default=None, max_length=512)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    database_name: str | None = Field(default=None, max_length=128)
    mqtt_ws_path: str | None = Field(default=None, max_length=128)
    mqtt_subscriptions: list[MqttSubscriptionItem] = Field(default_factory=list)

    @field_validator("port", mode="before")
    @classmethod
    def normalize_optional_port(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @field_validator("mqtt_subscriptions", mode="before")
    @classmethod
    def normalize_mqtt_subscriptions(cls, value: Any) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                topic = str(item.get("topic", "")).strip()
                name = str(item.get("name", "")).strip()
            else:
                topic = str(getattr(item, "topic", "")).strip()
                name = str(getattr(item, "name", "")).strip()
            if topic:
                cleaned.append({"topic": topic, "name": name or topic})
        return cleaned

    @field_validator("sub_links", mode="before")
    @classmethod
    def normalize_sub_links(cls, value: Any) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                url = str(item.get("url", "")).strip()
                clone_url = _optional_text(item.get("clone_url"))
                if name and url:
                    cleaned.append(
                        {
                            "name": name,
                            "url": url,
                            "clone_url": clone_url or None,
                            "is_reachable": item.get("is_reachable"),
                            "last_checked_at": item.get("last_checked_at"),
                        }
                    )
        return cleaned

    @field_validator("projects", "environments", mode="before")
    @classmethod
    def normalize_id_list(cls, value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, (int, str)):
            value = [value]
        if isinstance(value, list):
            result: list[int] = []
            for item in value:
                if item is None or item == "":
                    continue
                result.append(int(item))
            return result
        return []

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> int:
        if value is None or value == "":
            return 1
        if isinstance(value, str) and not value.isdigit():
            raise ValueError("type 必须是字典项 ID")
        return int(value)


class ConnectionCreate(ConnectionBase):
    group_id: int
    password: str | None = Field(default=None, max_length=512)

    @field_validator("group_id", mode="before")
    @classmethod
    def validate_group_id(cls, value: Any) -> int:
        if value is None or value == "":
            raise ValueError("请选择连接分组")
        return int(value)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, max_length=512)
    description: str | None = None
    projects: list[int] | None = None
    environments: list[int] | None = None
    type: int | None = None
    group_id: int | None = None
    is_shared: bool | None = None
    sort_order: int | None = None
    icon: str | None = None
    sub_links: list[SubLinkItem] | None = None
    host: str | None = Field(default=None, max_length=512)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    database_name: str | None = Field(default=None, max_length=128)
    mqtt_ws_path: str | None = Field(default=None, max_length=128)
    mqtt_subscriptions: list[MqttSubscriptionItem] | None = None

    @field_validator("mqtt_subscriptions", mode="before")
    @classmethod
    def normalize_mqtt_subscriptions_update(cls, value: Any) -> list | None:
        if value is None:
            return value
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                topic = str(item.get("topic", "")).strip()
                name = str(item.get("name", "")).strip()
            else:
                topic = str(getattr(item, "topic", "")).strip()
                name = str(getattr(item, "name", "")).strip()
            if topic:
                cleaned.append({"topic": topic, "name": name or topic})
        return cleaned

    @field_validator("projects", "environments", mode="before")
    @classmethod
    def normalize_id_list(cls, value: Any) -> list[int] | None:
        if value is None:
            return value
        if isinstance(value, (int, str)):
            value = [value]
        if isinstance(value, list):
            return [int(item) for item in value if item is not None and item != ""]
        return []

class ConnectionOut(ConnectionBase):
    id: int
    password_set: bool = False
    is_reachable: bool | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_connection(cls, conn: Any) -> "ConnectionOut":
        from app.services import connection_to_out_dict

        return cls.model_validate(connection_to_out_dict(conn))


class ConnectionTestRequest(BaseModel):
    type: int
    host: str = Field(min_length=1, max_length=512)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    database_name: str | None = Field(default=None, max_length=128)
    connection_id: int | None = None


class ConnectionTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: float | None = None


class ConnectionPingOut(BaseModel):
    id: int
    is_reachable: bool
    last_checked_at: datetime

    model_config = {"from_attributes": True}


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    scope: str
    items: list[ReorderItem]


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class HomeGroupOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    sort_order: int
    is_system: bool = False
    is_project_group: bool = False
    connections: list["ConnectionOut"] = Field(default_factory=list)


class HomeResponse(BaseModel):
    groups: list[HomeGroupOut]
    projects: list[DictItemOut]
    environments: list[DictItemOut]
    labels: list[DictItemOut]
    connection_groups: list[DictItemOut] = Field(default_factory=list)


class SubscriptionBase(BaseModel):
    enabled: bool = False
    github_repo: str | None = None
    github_branch: str | None = None
    github_events: list[str] | None = None
    db_filter: dict[str, Any] | None = None
    notify_homepage: bool = True


class SubscriptionCreate(SubscriptionBase):
    connection_id: int


class SubscriptionUpdate(BaseModel):
    enabled: bool | None = None
    github_repo: str | None = None
    github_branch: str | None = None
    github_events: list[str] | None = None
    db_filter: dict[str, Any] | None = None
    notify_homepage: bool | None = None
    link_enabled: dict[str, bool] | None = None


class GitlabSubscriptionLinkOut(BaseModel):
    link_key: str
    name: str
    url: str
    clone_url: str = ""
    branch: str
    repo_path: str = ""
    enabled: bool
    link_kind: str = "gitlab"
    cluster_id: int | None = None
    webhook_secret: str | None = None
    last_updated_at: datetime | None = None
    api_scan_status: str | None = None
    api_endpoint_count: int = 0


class GitlabSubscriptionTreeOut(BaseModel):
    id: int
    connection_id: int
    connection_name: str
    connection_type_name: str | None = None
    project_display: str
    environment_display: str
    links: list[GitlabSubscriptionLinkOut]


class SubscriptionOut(SubscriptionBase):
    id: int
    connection_id: int
    webhook_secret: str
    webhook_url: str | None = None
    connection_name: str | None = None
    connection_url: str | None = None
    connection_type_name: str | None = None
    provider: str | None = None
    project_display: str | None = None
    environment_display: str | None = None
    branch_display: str | None = None
    repo_web_url: str | None = None
    repo_base_url: str | None = None
    projects: list[int] = Field(default_factory=list)
    environments: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivityLogDiffOut(BaseModel):
    log_id: int
    commit_sha: str | None
    diff: str
    repo: str | None = None
    branch: str | None = None
    provider: str | None = None
    message: str | None = None


class ActivityLogOut(BaseModel):
    id: int
    subscription_id: int | None
    connection_id: int | None
    project: str
    environment: str
    source_type: str
    title: str
    summary: str | None
    payload: dict[str, Any] | None
    author: str | None
    occurred_at: datetime
    is_read: bool

    model_config = {"from_attributes": True}


class DatabaseWebhookPayload(BaseModel):
    connection_id: int | None = None
    webhook_secret: str | None = None
    operation: str
    table: str | None = None
    summary: str
    rows_affected: int | None = None
    sql_preview: str | None = None
    author: str | None = None


class SchemaMonitorConfigUpdate(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    include_databases: list[str] | None = None
    exclude_databases: list[str] | None = None


class SchemaMonitorPingRequest(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None


class SchemaMonitorPingOut(BaseModel):
    ok: bool
    message: str
    latency_ms: float | None = None


class SchemaMonitorOut(BaseModel):
    subscription_id: int
    enabled: bool
    host: str | None = None
    port: int = 3306
    username: str | None = None
    password_set: bool = False
    connection_configured: bool = False
    include_databases: list[str] = Field(default_factory=list)
    exclude_databases: list[str] = Field(default_factory=list)
    interval_seconds: int
    last_scan_at: datetime | None = None
    last_error: str | None = None
    has_baseline: bool = False
    database_count: int = 0
    table_count: int = 0


class SchemaScanResultOut(BaseModel):
    subscription_id: int
    changes_detected: int
    logs_created: int
    has_baseline: bool
    message: str


class SchemaResetBaselineOut(BaseModel):
    subscription_id: int
    deleted_logs: int
    changes_detected: int = 0
    logs_created: int = 0
    has_baseline: bool
    database_count: int = 0
    table_count: int = 0
    message: str


class OmnidbMenuUrlOut(BaseModel):
    url: str


class PublicConfigOut(BaseModel):
    webhook_base_url: str
    omnidb_base_url: str = ""
    omnidb_login_url: str = ""
    sshwifty_base_url: str = ""
    redpanda_base_url: str = ""
    redisinsight_base_url: str = ""


class EmbedSessionOut(BaseModel):
    session_id: str
    console_type: str
    connection_id: int
    connection_name: str
    embed_url: str
    is_temporary: bool = True


class OmnidbOpenOut(BaseModel):
    embed_url: str
    connection_name: str
    omnidb_connection_id: int | None = None
    session_id: str | None = None


class SshwiftyOpenOut(BaseModel):
    embed_url: str
    connection_name: str
    session_id: str | None = None


class KafkaConsoleConnectionOut(BaseModel):
    id: int
    name: str
    brokers: str
    username: str | None = None
    password_set: bool = False
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KafkaConsoleConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    brokers: str = Field(min_length=1, max_length=512)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class KafkaConsoleConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    brokers: str | None = Field(default=None, min_length=1, max_length=512)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class KafkaConsoleConnectionTestRequest(BaseModel):
    brokers: str = Field(min_length=1, max_length=512)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class MqttConsoleConnectionOut(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str | None = None
    password_set: bool = False
    mqtt_subscriptions: list[MqttSubscriptionItem] = Field(default_factory=list)
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MqttConsoleConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=256)
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class MqttConsoleConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    host: str | None = Field(default=None, min_length=1, max_length=256)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class MqttConsoleConnectionTestRequest(BaseModel):
    host: str = Field(min_length=1, max_length=256)
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)


class MqttConsoleSubscriptionsUpdate(BaseModel):
    subscriptions: list[MqttSubscriptionItem] = Field(default_factory=list)


class MqttConsoleConnectOut(BaseModel):
    connection_id: int
    connection_name: str
    host: str
    port: int
    broker_url: str
    username: str = ""
    password: str = ""
    subscriptions: list[MqttSubscriptionItem] = Field(default_factory=list)


class K8sClusterConfigBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    api_server: str = Field(min_length=1, max_length=512)
    provider: str = Field(default="native", max_length=32)
    auth_type: str = Field(default="password", max_length=16)
    username: str | None = Field(default=None, max_length=128)
    verify_ssl: bool = False

    @field_validator("api_server")
    @classmethod
    def normalize_api_server(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("集群地址不能为空")
        if not text.startswith(("http://", "https://")):
            text = f"https://{text}"
        return text.rstrip("/")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        text = (value or "native").strip().lower()
        allowed = {"native", "kubesphere", "kuboard"}
        if text not in allowed:
            raise ValueError(f"provider 必须是 {', '.join(sorted(allowed))}")
        return text

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, value: str) -> str:
        text = (value or "password").strip().lower()
        allowed = {"password", "token"}
        if text not in allowed:
            raise ValueError(f"auth_type 必须是 {', '.join(sorted(allowed))}")
        return text


class K8sClusterConfigCreate(K8sClusterConfigBase):
    password: str | None = Field(default=None, max_length=1024)


class K8sClusterConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    api_server: str | None = Field(default=None, min_length=1, max_length=512)
    provider: str | None = Field(default=None, max_length=32)
    auth_type: str | None = Field(default=None, max_length=16)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=1024)
    verify_ssl: bool | None = None

    @field_validator("api_server")
    @classmethod
    def normalize_api_server(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            raise ValueError("集群地址不能为空")
        if not text.startswith(("http://", "https://")):
            text = f"https://{text}"
        return text.rstrip("/")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = (value or "native").strip().lower()
        allowed = {"native", "kubesphere", "kuboard"}
        if text not in allowed:
            raise ValueError(f"provider 必须是 {', '.join(sorted(allowed))}")
        return text

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = (value or "password").strip().lower()
        allowed = {"password", "token"}
        if text not in allowed:
            raise ValueError(f"auth_type 必须是 {', '.join(sorted(allowed))}")
        return text


class K8sClusterConfigOut(K8sClusterConfigBase):
    id: int
    password_set: bool = False
    sort_order: int = 0
    last_connected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class K8sConnectOut(BaseModel):
    ok: bool
    message: str
    cluster_id: int
    version: str = ""
    namespace_count: int = 0
    projects: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: float | None = None
    last_connected_at: datetime | None = None


class K8sProjectOut(BaseModel):
    name: str
    status: str = ""
    created_at: datetime | None = None


class K8sContainerOut(BaseModel):
    name: str
    image: str = ""
    ready: bool = False
    restart_count: int = 0


class K8sPodOut(BaseModel):
    name: str
    namespace: str
    status: str = ""
    phase: str = ""
    node: str = ""
    pod_ip: str = ""
    host_ip: str = ""
    containers: list[K8sContainerOut] = Field(default_factory=list)
    restart_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class K8sServiceOut(BaseModel):
    id: str
    project: str
    namespace: str
    service_name: str
    service_type: str = ""
    cluster_ip: str = ""
    ports: list[str] = Field(default_factory=list)
    external_ports: list[int] = Field(default_factory=list)
    workload_kind: str | None = None
    workload_name: str | None = None
    status: str = ""
    ready_replicas: int = 0
    replicas: int = 0
    nodes: list[str] = Field(default_factory=list)
    pod_ips: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None
    pods: list[K8sPodOut] = Field(default_factory=list)
    scalable: bool = False


class K8sScaleRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=253)
    workload_kind: str = Field(min_length=1, max_length=32)
    workload_name: str = Field(min_length=1, max_length=253)
    delta: int = Field(ge=-50, le=50)


class K8sScaleOut(BaseModel):
    namespace: str
    workload_kind: str
    workload_name: str
    replicas: int
    message: str


class K8sPodLogOut(BaseModel):
    namespace: str
    pod_name: str
    container: str = ""
    logs: str


class K8sWatermarkValueOut(BaseModel):
    raw: str
    timestamp: int
    formatted_at: datetime
    lag_ms: int
    lag_hours: float
    delayed: bool = False


class K8sWatermarkOperatorOut(BaseModel):
    job_id: str = ""
    job_name: str = ""
    vertex_id: str
    operator_name: str
    watermarks: list[K8sWatermarkValueOut] = Field(default_factory=list)
    error: str = ""


class K8sWatermarkOut(BaseModel):
    cluster_id: int
    namespace: str
    service_name: str
    port: int
    flink_url: str
    generated_at: datetime
    jobs_count: int = 0
    items: list[K8sWatermarkOperatorOut] = Field(default_factory=list)


K8sRestartMonitorOption = Literal["none", "immediate", "5m", "10m"]


class K8sAlarmMonitorGroupOut(BaseModel):
    namespace: str
    enabled: bool = False
    service_count: int = 0
    monitored_service_count: int = 0


class K8sAlarmMonitorGroupUpdate(BaseModel):
    enabled: bool


class K8sAlarmMonitorServiceOut(BaseModel):
    service_name: str
    restart_monitor: K8sRestartMonitorOption = "none"
    watermark_minutes: int | None = None


class K8sAlarmMonitorServiceUpdate(BaseModel):
    restart_monitor: K8sRestartMonitorOption = "none"
    watermark_minutes: int | None = Field(default=None, ge=1, le=10080)


class K8sAlarmMonitorSyncOut(BaseModel):
    groups_count: int = 0
    services_count: int = 0
    namespaces: list[str] = Field(default_factory=list)


class K8sAlarmEventOut(BaseModel):
    id: int
    cluster_id: int
    cluster_name: str = ""
    namespace: str
    service_name: str
    alert_type: str
    status: str
    title: str
    summary: str | None = None
    payload: dict[str, Any] | None = None
    is_read: bool = False
    occurred_at: datetime
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


class RedpandaOpenOut(BaseModel):
    embed_url: str
    connection_name: str
    session_id: str | None = None


class RedisinsightOpenOut(BaseModel):
    embed_url: str
    connection_name: str
    database_id: str | None = None
    session_id: str | None = None


class MqttConsoleConfigOut(BaseModel):
    connection_id: int
    connection_name: str
    host: str
    port: int
    broker_url: str = ""
    ws_path: str
    username: str = ""
    password: str = ""
    subscriptions: list[MqttSubscriptionItem] = Field(default_factory=list)
    use_bridge: bool = True
    bridge_path: str = ""


class MqttOpenOut(MqttConsoleConfigOut):
    session_id: str | None = None


class RepoAccessSettingsOut(BaseModel):
    gitlab_base_url: str
    gitlab_token_set: bool
    gitlab_token_hint: str | None = None
    gitlab_ssh_key_set: bool = False
    github_token_set: bool
    github_token_hint: str | None = None
    public_webhook_base_url: str
    updated_at: datetime | None = None


class RepoAccessSettingsUpdate(BaseModel):
    gitlab_base_url: str | None = None
    gitlab_token: str | None = None
    gitlab_ssh_private_key: str | None = None
    github_token: str | None = None
    public_webhook_base_url: str | None = None


class ApiMonitorParameterOut(BaseModel):
    name: str
    in_: str = Field(alias="in")
    required: bool = False
    data_type: str = "any"
    description: str = ""
    schema_name: str | None = None
    children: list["ApiMonitorParameterOut"] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ApiMonitorResponseOut(BaseModel):
    status_code: str
    description: str = ""
    data_type: str = ""
    schema_name: str | None = None
    properties: list[ApiMonitorParameterOut] = Field(default_factory=list)


class ApiMonitorEndpointOut(BaseModel):
    id: str
    method: str
    path: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    request_content_type: str = ""
    response_content_type: str = ""
    parameters: list[ApiMonitorParameterOut] = Field(default_factory=list)
    responses: list[ApiMonitorResponseOut] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)


class ApiMonitorGroupOut(BaseModel):
    tag: str
    endpoints: list[ApiMonitorEndpointOut] = Field(default_factory=list)


class ApiMonitorSpecOut(BaseModel):
    spec_version: int = 1
    meta: dict[str, Any] = Field(default_factory=dict)
    groups: list[ApiMonitorGroupOut] = Field(default_factory=list)
    endpoints: list[ApiMonitorEndpointOut] = Field(default_factory=list)
    endpoint_count: int = 0


class ApiMonitorServiceOut(BaseModel):
    id: str
    connection_id: int
    subscription_id: int | None = None
    link_key: str
    name: str
    connection_name: str
    repo_path: str
    branch: str | None = None
    provider: str | None = None
    projects: list[int] = Field(default_factory=list)
    environments: list[int] = Field(default_factory=list)
    project_display: str = ""
    environment_display: str = ""
    connection_type_name: str | None = None
    endpoint_count: int = 0
    last_scan_at: datetime | None = None
    scan_status: str | None = None
    has_snapshot: bool = False


class ApiMonitorFilterOptionOut(BaseModel):
    id: int
    name: str


class ApiMonitorNameOptionOut(BaseModel):
    id: str
    label: str


class ApiMonitorFilterOptionsOut(BaseModel):
    projects: list[ApiMonitorFilterOptionOut] = Field(default_factory=list)
    environments: list[ApiMonitorFilterOptionOut] = Field(default_factory=list)
    names: list[ApiMonitorNameOptionOut] = Field(default_factory=list)


class ApiMonitorGroupSummaryOut(BaseModel):
    tag: str
    endpoint_count: int = 0


class ApiMonitorModuleSummaryOut(BaseModel):
    name: str
    endpoint_count: int = 0


class ApiMonitorModulesOut(BaseModel):
    service_id: str
    modules: list[ApiMonitorModuleSummaryOut] = Field(default_factory=list)


class ApiMonitorGroupsOut(BaseModel):
    service_id: str
    module: str | None = None
    display_name: str = ""
    endpoint_count: int = 0
    has_snapshot: bool = False
    scan_status: str | None = None
    repo_path: str = ""
    branch: str | None = None
    project_display: str = ""
    environment_display: str = ""
    groups: list[ApiMonitorGroupSummaryOut] = Field(default_factory=list)
    removed_endpoint_keys: list[str] = Field(default_factory=list)


class ApiMonitorEndpointSummaryOut(BaseModel):
    id: str
    method: str
    path: str
    summary: str


class ApiMonitorGroupEndpointsOut(BaseModel):
    tag: str
    endpoints: list[ApiMonitorEndpointSummaryOut] = Field(default_factory=list)


class ApiMonitorProxyIn(BaseModel):
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class ApiMonitorProxyOut(BaseModel):
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    elapsed_ms: int = 0


class ApiMonitorSyncResultOut(BaseModel):
    subscription_id: int
    synced: int
    skipped: int = 0
    failed: int = 0
    message: str


class ApiMonitorScanRunOut(BaseModel):
    id: int
    subscription_id: int
    link_key: str
    commit_sha: str | None = None
    commit_message: str | None = None
    branch: str | None = None
    is_baseline: bool = False
    endpoint_count_before: int = 0
    endpoint_count_after: int = 0
    added_count: int = 0
    modified_count: int = 0
    removed_count: int = 0
    scanned_at: datetime


class ApiMonitorEndpointChangeOut(BaseModel):
    id: int
    scan_run_id: int
    endpoint_key: str
    change_type: str
    tag: str
    summary: str
    source_file: str | None = None
    source_line: int | None = None
    created_at: datetime
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    diff_json: dict[str, Any] | None = None
    scan_run: ApiMonitorScanRunOut | None = None


class ApiMonitorScanRunChangesOut(BaseModel):
    scan_run: ApiMonitorScanRunOut
    changes: list[ApiMonitorEndpointChangeOut] = Field(default_factory=list)


ApiMonitorParameterOut.model_rebuild()


class ApiTestCaseCreate(BaseModel):
    project_id: int
    environment_id: int
    service: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    api_path: str = Field(min_length=1, max_length=512)
    method: str = Field(min_length=1, max_length=16)
    request_headers: str | None = None
    request_params: str | None = None
    request_body: str | None = None
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_response: str | None = None
    response_assert_mode: str = Field(default="text", max_length=16)
    response_assert_rules: str | None = None
    case_type: str = Field(default="smoke", max_length=32)
    endpoint_id: str | None = Field(default=None, max_length=512)


class ApiTestCaseUpdate(BaseModel):
    project_id: int | None = None
    environment_id: int | None = None
    service: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    api_path: str | None = Field(default=None, min_length=1, max_length=512)
    method: str | None = Field(default=None, min_length=1, max_length=16)
    request_headers: str | None = None
    request_params: str | None = None
    request_body: str | None = None
    expected_status: int | None = Field(default=None, ge=100, le=599)
    expected_response: str | None = None
    response_assert_mode: str | None = Field(default=None, max_length=16)
    response_assert_rules: str | None = None
    case_type: str | None = Field(default=None, max_length=32)
    endpoint_id: str | None = Field(default=None, max_length=512)


class ApiTestCaseExecutionResultIn(BaseModel):
    passed: bool
    status_code: int | None = Field(default=None, ge=100, le=599)
    response: str | None = None
    detail: str | None = None


class ApiTestCaseOut(BaseModel):
    id: int
    project_id: int
    environment_id: int
    project_display: str = ""
    environment_display: str = ""
    service: str
    name: str
    api_path: str
    method: str
    request_headers: str | None = None
    request_params: str | None = None
    request_body: str | None = None
    expected_status: int
    expected_response: str | None = None
    response_assert_mode: str = "text"
    response_assert_rules: str | None = None
    case_type: str
    status: str
    endpoint_id: str | None = None
    last_exec_pass: bool | None = None
    last_exec_status_code: int | None = None
    last_exec_response: str | None = None
    last_exec_detail: str | None = None
    last_exec_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ApiTestCaseListOut(BaseModel):
    items: list[ApiTestCaseOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10


class ApiTestCaseGenerateIn(BaseModel):
    endpoint_id: str = Field(min_length=1, max_length=512)
    project_id: int
    environment_id: int
    service: str = Field(min_length=1, max_length=128)
    method: str = Field(min_length=1, max_length=16)
    api_path: str = Field(min_length=1, max_length=512)
    summary: str = ""
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_response: str | None = None
    overwrite: bool = False


class ApiTestCaseGenerateOut(BaseModel):
    items: list[ApiTestCaseOut] = Field(default_factory=list)
    created: int = 0
    overwritten: int = 0


class ApiTestCaseBatchDeleteOut(BaseModel):
    soft_deleted: int = 0
    hard_deleted: int = 0
    not_found: int = 0
    total: int = 0


class AiAnalysisIn(BaseModel):
    log_id: int | None = None
    scenario: str = "generic"
    title: str = ""
    summary: str = ""
    context: str = ""
    content: str = ""
    content_label: str = "变更内容"
    prompt_type: str = "AI分析"
    extra: dict[str, Any] = Field(default_factory=dict)


class AiAnalysisOut(BaseModel):
    analysis: str
    interpretation: dict[str, Any] | None = None
    model: str = ""
    prompt_type: str = "AI分析"
    prompt_name: str = ""
    scenario: str = ""
    truncated: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class LlmConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(min_length=1, max_length=500)
    model_name: str = Field(min_length=1, max_length=100)
    context_limit: int = Field(default=128000, ge=1)
    vision_enabled: bool = False
    stream_enabled: bool = True
    enabled: bool = False


class LlmConfigUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)
    model_name: str = Field(min_length=1, max_length=100)
    context_limit: int = Field(default=128000, ge=1)
    vision_enabled: bool = False
    stream_enabled: bool = True
    enabled: bool = False


class LlmConfigOut(BaseModel):
    id: str
    name: str
    api_url: str
    api_key: str = ""
    has_api_key: bool = False
    model_name: str
    context_limit: int
    vision_enabled: bool
    stream_enabled: bool
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LlmToggleIn(BaseModel):
    enabled: bool


class LlmConnectionTestIn(BaseModel):
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)
    model_name: str = Field(min_length=1, max_length=100)
    config_id: str | None = None


class LlmModelsFetchIn(BaseModel):
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)
    config_id: str | None = None


class LlmModelsOut(BaseModel):
    items: list[str] = Field(default_factory=list)


class LlmConnectionTestOut(BaseModel):
    ok: bool
    message: str
    model: str | None = None


class PromptTemplateIn(BaseModel):
    prompt_type: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=20000)
    base_content: str = Field(default="", max_length=10000)
    response_type: str = Field(default="", max_length=100)
    response_format: str = Field(default="", max_length=10000)
    remark: str = Field(default="", max_length=200)
    enabled: bool = True
    is_default: bool = False
    is_preset: bool = False


class PromptTemplateOut(BaseModel):
    id: str
    prompt_type: str
    name: str
    description: str = ""
    content: str = ""
    base_content: str = ""
    response_type: str = ""
    response_format: str = ""
    remark: str = ""
    enabled: bool = True
    is_default: bool = False
    is_preset: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
