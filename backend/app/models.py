from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DictItem(Base):
    __tablename__ = "dict_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dict_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    projects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    environments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    type: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sub_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    host: Mapped[str | None] = mapped_column(String(256), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(512), nullable=True)
    database_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mqtt_ws_path: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mqtt_subscriptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    embed_sessions: Mapped[list["EmbedConsoleSession"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="connection", uselist=False, cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("connections.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    github_repo: Mapped[str | None] = mapped_column(String(256), nullable=True)
    github_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    github_events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    link_enabled: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    db_filter: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    notify_homepage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    connection: Mapped["Connection"] = relationship(back_populates="subscription")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    connection_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    project: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    connection: Mapped["Connection | None"] = relationship(back_populates="activity_logs")


class SchemaSnapshot(Base):
    __tablename__ = "schema_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ApiSnapshot(Base):
    __tablename__ = "api_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_key: Mapped[str] = mapped_column(String(32), nullable=False, default="main")
    spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    scan_runs: Mapped[list["ApiScanRun"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class ApiScanRun(Base):
    __tablename__ = "api_scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_key: Mapped[str] = mapped_column(String(32), nullable=False, default="main", index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    commit_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    endpoint_count_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    endpoint_count_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    snapshot: Mapped["ApiSnapshot"] = relationship(back_populates="scan_runs")
    endpoint_changes: Mapped[list["ApiEndpointChange"]] = relationship(
        back_populates="scan_run", cascade="all, delete-orphan"
    )


class ApiEndpointChange(Base):
    __tablename__ = "api_endpoint_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_scan_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_key: Mapped[str] = mapped_column(String(32), nullable=False, default="main", index=True)
    endpoint_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scan_run: Mapped["ApiScanRun"] = relationship(back_populates="endpoint_changes")


class ApiTestCase(Base):
    """接口自动化用例（手工维护 + 后续扫描同步）。"""

    __tablename__ = "api_test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    environment_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    api_path: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    request_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    expected_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_assert_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    response_assert_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_type: Mapped[str] = mapped_column(String(32), nullable=False, default="smoke", index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    endpoint_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    last_exec_pass: Mapped[bool | None] = mapped_column(nullable=True)
    last_exec_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_exec_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_exec_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_exec_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KafkaConsoleConnection(Base):
    """连接方式 → Kafka 菜单专用，与 connections 表互不影响。"""

    __tablename__ = "kafka_console_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    brokers: Mapped[str] = mapped_column(String(512), nullable=False)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class MqttConsoleConnection(Base):
    """连接方式 → MQTT 菜单专用，与 connections 表互不影响。"""

    __tablename__ = "mqtt_console_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=1883)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mqtt_subscriptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class K8sClusterConfig(Base):
    """服务监控菜单专用的 Kubernetes 集群连接配置。"""

    __tablename__ = "k8s_cluster_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    api_server: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="native")
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="password")
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    connection_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    alarm_monitor_groups: Mapped[list["K8sAlarmMonitorGroup"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )
    alarm_monitor_services: Mapped[list["K8sAlarmMonitorService"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )


class K8sAlarmMonitorGroup(Base):
    __tablename__ = "k8s_alarm_monitor_groups"
    __table_args__ = (
        UniqueConstraint("cluster_id", "namespace", name="uq_k8s_alarm_monitor_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("k8s_cluster_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    cluster: Mapped["K8sClusterConfig"] = relationship(back_populates="alarm_monitor_groups")


class K8sAlarmMonitorService(Base):
    __tablename__ = "k8s_alarm_monitor_services"
    __table_args__ = (
        UniqueConstraint(
            "cluster_id",
            "namespace",
            "service_name",
            name="uq_k8s_alarm_monitor_service",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("k8s_cluster_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    restart_monitor: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    watermark_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    cluster: Mapped["K8sClusterConfig"] = relationship(back_populates="alarm_monitor_services")


class K8sAlarmMonitorSnapshot(Base):
    __tablename__ = "k8s_alarm_monitor_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "cluster_id",
            "namespace",
            "service_name",
            name="uq_k8s_alarm_monitor_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("k8s_cluster_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    restart_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pod_restart_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_restart_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_watermark_lag_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restart_alert_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watermark_alert_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_exception_timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exception_alert_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class K8sAlarmEvent(Base):
    __tablename__ = "k8s_alarm_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("k8s_cluster_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EmbedConsoleSession(Base):
    __tablename__ = "embed_console_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    console_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    is_temporary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_alias: Mapped[str | None] = mapped_column(String(256), nullable=True)
    embed_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    snapshot_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    connection: Mapped["Connection"] = relationship(back_populates="embed_sessions")


class RepoAccessSettings(Base):
    __tablename__ = "repo_access_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    gitlab_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    gitlab_token: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    gitlab_ssh_private_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    github_token: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    public_webhook_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class LlmConfig(Base):
    __tablename__ = "llm_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    context_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=128000)
    vision_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stream_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    extra_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
