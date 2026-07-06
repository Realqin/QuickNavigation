export interface SubLink {
  name: string;
  url: string;
  clone_url?: string | null;
  is_reachable?: boolean | null;
  last_checked_at?: string | null;
}

export interface MqttSubscription {
  topic: string;
  name?: string | null;
}

export type DictType = 'project' | 'environment' | 'label' | 'connection_group';

export interface DictItem {
  id: number;
  type: DictType;
  name: string;
  description?: string | null;
  sort_order: number;
  is_system?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Connection {
  id: number;
  name: string;
  url: string;
  description?: string | null;
  projects: number[];
  environments: number[];
  type: number;
  group_id?: number | null;
  is_shared: boolean;
  sort_order: number;
  icon?: string | null;
  host?: string | null;
  port?: number | null;
  username?: string | null;
  database_name?: string | null;
  mqtt_ws_path?: string | null;
  mqtt_subscriptions?: MqttSubscription[];
  password_set?: boolean;
  is_reachable?: boolean | null;
  last_checked_at?: string | null;
  sub_links: SubLink[];
  created_at: string;
  updated_at: string;
}

export interface ConnectionPingResult {
  id: number;
  is_reachable: boolean;
  last_checked_at: string;
}

export interface HomeGroup {
  id: number;
  name: string;
  description?: string | null;
  sort_order: number;
  is_system: boolean;
  is_project_group: boolean;
  connections: Connection[];
}

export interface HomeData {
  groups: HomeGroup[];
  projects: DictItem[];
  environments: DictItem[];
  labels: DictItem[];
  connection_groups: DictItem[];
}

export interface ActivityLog {
  id: number;
  subscription_id?: number | null;
  connection_id?: number | null;
  project: string;
  environment: string;
  source_type: string;
  title: string;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
  author?: string | null;
  occurred_at: string;
  is_read: boolean;
}

export interface ActivityLogDiff {
  log_id: number;
  commit_sha?: string | null;
  diff: string;
  repo?: string | null;
  branch?: string | null;
  provider?: string | null;
  message?: string | null;
}

export interface GitlabSubscriptionLink {
  link_key: string;
  name: string;
  url: string;
  clone_url?: string;
  branch: string;
  repo_path?: string;
  enabled: boolean;
  link_kind?: 'gitlab' | 'database' | 'k8s';
  cluster_id?: number | null;
  webhook_secret?: string | null;
  last_updated_at?: string | null;
  api_scan_status?: string | null;
  api_endpoint_count?: number;
}

export interface GitlabSubscriptionTree {
  id: number;
  connection_id: number;
  connection_name: string;
  connection_type_name?: string | null;
  project_display: string;
  environment_display: string;
  links: GitlabSubscriptionLink[];
}

export interface RepoAccessSettings {
  gitlab_base_url: string;
  gitlab_token_set: boolean;
  gitlab_token_hint?: string | null;
  gitlab_ssh_key_set: boolean;
  github_token_set: boolean;
  github_token_hint?: string | null;
  public_webhook_base_url: string;
  updated_at?: string | null;
}

export interface Subscription {
  id: number;
  connection_id: number;
  enabled: boolean;
  github_repo?: string | null;
  github_branch?: string | null;
  github_events?: string[] | null;
  db_filter?: Record<string, unknown> | null;
  notify_homepage: boolean;
  webhook_secret: string;
  webhook_url?: string | null;
  connection_name?: string | null;
  connection_url?: string | null;
  connection_type_name?: string | null;
  provider?: string | null;
  project_display?: string | null;
  environment_display?: string | null;
  branch_display?: string | null;
  repo_web_url?: string | null;
  repo_base_url?: string | null;
  projects?: number[];
  environments?: number[];
  created_at: string;
  updated_at: string;
}

export interface ConnectionFormValues {
  name: string;
  url?: string;
  description?: string;
  projects: number[];
  environments: number[];
  type: number;
  group_id: number;
  sub_links?: SubLink[];
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  database_name?: string;
  mqtt_ws_path?: string;
  mqtt_subscriptions?: MqttSubscription[];
}

export interface MqttConsoleConfig {
  connection_id: number;
  connection_name: string;
  host: string;
  port: number;
  broker_url?: string;
  ws_path: string;
  username: string;
  password: string;
  subscriptions: MqttSubscription[];
  use_bridge?: boolean;
  bridge_path?: string;
}

export interface ConnectionTestPayload {
  type: number;
  host: string;
  port?: number;
  username?: string;
  password?: string;
  database_name?: string;
  connection_id?: number;
}

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  latency_ms?: number | null;
}

export interface DictFormValues {
  type: DictType;
  name: string;
  description?: string;
  sort_order: number;
}

export interface PublicConfig {
  webhook_base_url: string;
  omnidb_base_url?: string;
  omnidb_login_url?: string;
  sshwifty_base_url?: string;
  redpanda_base_url?: string;
  redisinsight_base_url?: string;
}

export interface EmbedSession {
  session_id: string;
  console_type: string;
  connection_id: number;
  connection_name: string;
  embed_url: string;
  is_temporary: boolean;
}

export interface OmnidbOpenResult {
  embed_url: string;
  connection_name: string;
  omnidb_connection_id?: number | null;
  session_id?: string | null;
}

export interface SshwiftyOpenResult {
  embed_url: string;
  connection_name: string;
  session_id?: string | null;
}

export interface RedpandaOpenResult {
  embed_url: string;
  connection_name: string;
  session_id?: string | null;
}

export interface KafkaConsoleConnection {
  id: number;
  name: string;
  brokers: string;
  username?: string | null;
  password_set: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface KafkaConsoleConnectionFormValues {
  name: string;
  brokers: string;
  username?: string;
  password?: string;
}

export interface KafkaConsoleConnectionTestPayload {
  brokers: string;
  username?: string;
  password?: string;
}

export interface MqttConsoleConnection {
  id: number;
  name: string;
  host: string;
  port: number;
  username?: string | null;
  password_set: boolean;
  mqtt_subscriptions: MqttSubscription[];
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface MqttConsoleConnectionFormValues {
  name: string;
  host: string;
  port: number;
  username?: string;
  password?: string;
}

export interface MqttConsoleConnectionTestPayload {
  host: string;
  port: number;
  username?: string;
  password?: string;
}

export interface MqttConsoleConnectResult {
  connection_id: number;
  connection_name: string;
  host: string;
  port: number;
  broker_url: string;
  username: string;
  password: string;
  subscriptions: MqttSubscription[];
}

export interface RedisinsightOpenResult {
  embed_url: string;
  connection_name: string;
  database_id?: string | null;
  session_id?: string | null;
}

export interface MqttOpenResult extends MqttConsoleConfig {
  session_id?: string | null;
}

export interface SchemaMonitorStatus {
  subscription_id: number;
  enabled: boolean;
  host?: string | null;
  port: number;
  username?: string | null;
  password_set: boolean;
  connection_configured: boolean;
  include_databases: string[];
  exclude_databases: string[];
  interval_seconds: number;
  last_scan_at?: string | null;
  last_error?: string | null;
  has_baseline: boolean;
  database_count: number;
  table_count: number;
}

export interface SchemaMonitorPingResult {
  ok: boolean;
  message: string;
  latency_ms?: number | null;
}

export interface SchemaScanResult {
  subscription_id: number;
  changes_detected: number;
  logs_created: number;
  has_baseline: boolean;
  message: string;
}

export interface SchemaResetBaselineResult {
  subscription_id: number;
  deleted_logs: number;
  changes_detected: number;
  logs_created: number;
  has_baseline: boolean;
  database_count: number;
  table_count: number;
  message: string;
}

export const PROJECT_CONNECTION_GROUP_NAME = '项目连接';

export const DICT_TYPE_LABELS: Record<DictType, string> = {
  project: '项目',
  environment: '环境',
  label: '类型',
  connection_group: '连接分组',
};
