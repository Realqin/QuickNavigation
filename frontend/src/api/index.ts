import axios from 'axios';
import { resolveApiBaseUrl } from '../utils/apiBase';
import { buildLogsWebSocketUrl } from '../utils/appWebSocket';
import type {
  ActivityLog,
  ActivityLogDiff,
  Connection,
  ConnectionFormValues,
  ConnectionTestPayload,
  ConnectionTestResult,
  DictFormValues,
  DictItem,
  DictType,
  HomeData,
  KafkaConsoleConnection,
  KafkaConsoleConnectionFormValues,
  KafkaConsoleConnectionTestPayload,
  MqttConsoleConnectResult,
  MqttConsoleConnection,
  MqttConsoleConnectionFormValues,
  MqttConsoleConnectionTestPayload,
  MqttSubscription,
  OmnidbOpenResult,
  EmbedSession,
  MqttConsoleConfig,
  MqttOpenResult,
  RedpandaOpenResult,
  RedisinsightOpenResult,
  SshwiftyOpenResult,
  GitlabSubscriptionTree,
  PublicConfig,
  RepoAccessSettings,
  SchemaMonitorPingResult,
  SchemaMonitorStatus,
  SchemaScanResult,
} from '../types';

const client = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 15000,
});

export async function fetchHome(project: number, environment: number): Promise<HomeData> {
  const { data } = await client.get<HomeData>('/api/connections/home', {
    params: { project, environment },
  });
  return data;
}

export const FILTER_EMPTY = 0;

export async function fetchConnections(params?: {
  name?: string;
  project?: number;
  environment?: number;
  is_shared?: boolean;
  group_id?: number;
}): Promise<Connection[]> {
  const { data } = await client.get<Connection[]>('/api/connections', { params });
  return data;
}

export async function fetchConnection(id: number): Promise<Connection> {
  const { data } = await client.get<Connection>(`/api/connections/${id}`);
  return data;
}

export async function createConnection(payload: ConnectionFormValues): Promise<Connection> {
  const { data } = await client.post<Connection>('/api/connections', payload);
  return data;
}

export async function updateConnection(
  id: number,
  payload: Partial<ConnectionFormValues>,
): Promise<Connection> {
  const { data } = await client.patch<Connection>(`/api/connections/${id}`, payload);
  return data;
}

export async function deleteConnection(id: number): Promise<void> {
  await client.delete(`/api/connections/${id}`);
}

export async function batchDeleteConnections(ids: number[]): Promise<void> {
  await client.post('/api/connections/batch-delete', { ids });
}

export async function openOmnidbConsole(
  connectionId: number,
  publicHost?: string,
): Promise<OmnidbOpenResult> {
  const { data } = await client.post<OmnidbOpenResult>(
    `/api/connections/${connectionId}/omnidb-open`,
    null,
    {
      params: publicHost ? { public_host: publicHost } : undefined,
    },
  );
  return data;
}

export async function fetchMqttConsoleConfig(connectionId: number): Promise<MqttConsoleConfig> {
  const { data } = await client.get<MqttConsoleConfig>(
    `/api/connections/${connectionId}/mqtt-config`,
  );
  return data;
}

export async function openMqttConsoleSession(connectionId: number): Promise<MqttOpenResult> {
  const { data } = await client.post<MqttOpenResult>(
    `/api/connections/${connectionId}/mqtt-open`,
    null,
  );
  return data;
}

export async function fetchEmbedSession(sessionId: string): Promise<EmbedSession> {
  const { data } = await client.get<EmbedSession>(`/api/embed-sessions/${sessionId}`);
  return data;
}

export async function closeEmbedSession(sessionId: string): Promise<void> {
  await client.delete(`/api/embed-sessions/${sessionId}`);
}

export async function openRedpandaConsole(
  connectionId: number,
  publicHost?: string,
): Promise<RedpandaOpenResult> {
  const { data } = await client.post<RedpandaOpenResult>(
    `/api/connections/${connectionId}/redpanda-open`,
    null,
    {
      params: publicHost ? { public_host: publicHost } : undefined,
      timeout: 30000,
    },
  );
  return data;
}

/** 连接方式菜单：持久化同步后返回控制台地址 */
export async function connectRedpandaConsole(
  connectionId: number,
  publicHost?: string,
): Promise<RedpandaOpenResult> {
  const { data } = await client.post<RedpandaOpenResult>(
    `/api/connections/${connectionId}/redpanda-connect`,
    null,
    {
      params: publicHost ? { public_host: publicHost } : undefined,
      timeout: 30000,
    },
  );
  return data;
}

export async function fetchKafkaConsoleConnections(): Promise<KafkaConsoleConnection[]> {
  const { data } = await client.get<KafkaConsoleConnection[]>('/api/kafka-console/connections');
  return data;
}

export async function createKafkaConsoleConnection(
  values: KafkaConsoleConnectionFormValues,
): Promise<KafkaConsoleConnection> {
  const { data } = await client.post<KafkaConsoleConnection>('/api/kafka-console/connections', values);
  return data;
}

export async function updateKafkaConsoleConnection(
  id: number,
  values: Partial<KafkaConsoleConnectionFormValues>,
): Promise<KafkaConsoleConnection> {
  const { data } = await client.put<KafkaConsoleConnection>(
    `/api/kafka-console/connections/${id}`,
    values,
  );
  return data;
}

export async function deleteKafkaConsoleConnection(id: number): Promise<void> {
  await client.delete(`/api/kafka-console/connections/${id}`);
}

export async function testKafkaConsoleConnection(
  payload: KafkaConsoleConnectionTestPayload,
): Promise<ConnectionTestResult> {
  const { data } = await client.post<ConnectionTestResult>(
    '/api/kafka-console/connections/test',
    payload,
  );
  return data;
}

export async function connectKafkaConsole(
  connectionId: number,
  publicHost?: string,
): Promise<RedpandaOpenResult> {
  const { data } = await client.post<RedpandaOpenResult>(
    `/api/kafka-console/connections/${connectionId}/connect`,
    null,
    {
      params: publicHost ? { public_host: publicHost } : undefined,
      timeout: 30000,
    },
  );
  return data;
}

export async function disconnectKafkaConsole(): Promise<void> {
  await client.post('/api/kafka-console/disconnect', null, { timeout: 30000 });
}

export function beaconDisconnectKafkaConsole(): void {
  if (typeof navigator.sendBeacon === 'function') {
    navigator.sendBeacon('/api/kafka-console/disconnect');
    return;
  }
  disconnectKafkaConsole().catch(() => undefined);
}

export async function fetchMqttConsoleConnections(): Promise<MqttConsoleConnection[]> {
  const { data } = await client.get<MqttConsoleConnection[]>('/api/mqtt-console/connections');
  return data;
}

export async function createMqttConsoleConnection(
  values: MqttConsoleConnectionFormValues,
): Promise<MqttConsoleConnection> {
  const { data } = await client.post<MqttConsoleConnection>('/api/mqtt-console/connections', values);
  return data;
}

export async function updateMqttConsoleConnection(
  id: number,
  values: Partial<MqttConsoleConnectionFormValues>,
): Promise<MqttConsoleConnection> {
  const { data } = await client.put<MqttConsoleConnection>(
    `/api/mqtt-console/connections/${id}`,
    values,
  );
  return data;
}

export async function deleteMqttConsoleConnection(id: number): Promise<void> {
  await client.delete(`/api/mqtt-console/connections/${id}`);
}

export async function testMqttConsoleConnection(
  payload: MqttConsoleConnectionTestPayload,
): Promise<ConnectionTestResult> {
  const { data } = await client.post<ConnectionTestResult>(
    '/api/mqtt-console/connections/test',
    payload,
  );
  return data;
}

export async function connectMqttConsole(connectionId: number): Promise<MqttConsoleConnectResult> {
  const { data } = await client.post<MqttConsoleConnectResult>(
    `/api/mqtt-console/connections/${connectionId}/connect`,
    null,
    { timeout: 30000 },
  );
  return data;
}

export async function updateMqttConsoleSubscriptions(
  connectionId: number,
  subscriptions: MqttSubscription[],
): Promise<MqttConsoleConnection> {
  const { data } = await client.put<MqttConsoleConnection>(
    `/api/mqtt-console/connections/${connectionId}/subscriptions`,
    { subscriptions },
  );
  return data;
}

export async function openRedisinsightConsole(
  connectionId: number,
  publicHost?: string,
): Promise<RedisinsightOpenResult> {
  const { data } = await client.post<RedisinsightOpenResult>(
    `/api/connections/${connectionId}/redisinsight-open`,
    null,
    {
      params: publicHost ? { public_host: publicHost } : undefined,
      timeout: 30000,
    },
  );
  return data;
}

export async function openSshwiftyConsole(
  connectionId: number,
  publicHost?: string,
): Promise<SshwiftyOpenResult> {
  const { data } = await client.post<SshwiftyOpenResult>(
    `/api/connections/${connectionId}/sshwifty-open`,
    null,
    {
      params: publicHost ? { public_host: publicHost } : undefined,
    },
  );
  return data;
}

export async function testConnection(
  payload: ConnectionTestPayload,
): Promise<ConnectionTestResult> {
  const { data } = await client.post<ConnectionTestResult>(
    '/api/connections/test-connection',
    payload,
  );
  return data;
}

export async function pingConnection(id: number, subIndex?: number): Promise<Connection> {
  const { data } = await client.post<Connection>(`/api/connections/${id}/ping`, null, {
    params: subIndex !== undefined ? { sub_index: subIndex } : {},
  });
  return data;
}

export async function reorderConnections(
  scope: string,
  items: { id: number; sort_order: number }[],
): Promise<void> {
  await client.patch('/api/connections/reorder', { scope, items });
}

export async function fetchLogs(params?: {
  project?: number;
  environment?: number;
  source_type?: string;
  limit?: number;
}): Promise<ActivityLog[]> {
  const { data } = await client.get<ActivityLog[]>('/api/logs', { params });
  return data;
}

export async function markLogRead(id: number): Promise<ActivityLog> {
  const { data } = await client.patch<ActivityLog>(`/api/logs/${id}/read`);
  return data;
}

export async function fetchLogDiff(logId: number): Promise<ActivityLogDiff> {
  const { data } = await client.get<ActivityLogDiff>(`/api/logs/${logId}/diff`);
  return data;
}

export async function fetchSubscriptions(params?: {
  project?: number;
  enabled?: boolean;
}): Promise<GitlabSubscriptionTree[]> {
  const { data } = await client.get<GitlabSubscriptionTree[]>('/api/subscriptions', { params });
  return data;
}

export async function updateSubscription(
  id: number,
  payload: Partial<{
    enabled: boolean;
    github_repo: string;
    github_events: string[];
    notify_homepage: boolean;
    link_enabled: Record<string, boolean>;
  }>,
): Promise<GitlabSubscriptionTree> {
  const { data } = await client.patch<GitlabSubscriptionTree>(`/api/subscriptions/${id}`, payload);
  return data;
}

export function createLogsWebSocket(onMessage: (log: ActivityLog) => void): WebSocket {
  const ws = new WebSocket(buildLogsWebSocketUrl());
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'log:new' && msg.data) {
        onMessage(msg.data as ActivityLog);
      }
    } catch {
      // ignore malformed messages
    }
  };
  return ws;
}

export async function fetchDictItems(type?: DictType): Promise<DictItem[]> {
  const { data } = await client.get<DictItem[]>('/api/dict', { params: type ? { type } : {} });
  return data;
}

export async function createDictItem(payload: DictFormValues): Promise<DictItem> {
  const { data } = await client.post<DictItem>('/api/dict', payload);
  return data;
}

export async function updateDictItem(
  id: number,
  payload: Partial<DictFormValues>,
): Promise<DictItem> {
  const { data } = await client.patch<DictItem>(`/api/dict/${id}`, payload);
  return data;
}

export async function deleteDictItem(id: number): Promise<void> {
  await client.delete(`/api/dict/${id}`);
}

export async function fetchPublicConfig(): Promise<PublicConfig> {
  const { data } = await client.get<PublicConfig>('/api/public/config');
  return data;
}

export async function fetchOmnidbMenuUrl(): Promise<{ url: string }> {
  const { data } = await client.get<{ url: string }>('/api/public/omnidb-menu-url');
  return data;
}

export async function fetchRepoAccessSettings(): Promise<RepoAccessSettings> {
  const { data } = await client.get<RepoAccessSettings>('/api/settings/repo-access');
  return data;
}

export async function fetchSchemaMonitor(subscriptionId: number): Promise<SchemaMonitorStatus> {
  const { data } = await client.get<SchemaMonitorStatus>(
    `/api/subscriptions/${subscriptionId}/schema-monitor`,
  );
  return data;
}

export async function updateSchemaMonitor(
  subscriptionId: number,
  payload: {
    host?: string;
    port?: number;
    username?: string;
    password?: string;
    include_databases?: string[];
    exclude_databases?: string[];
  },
): Promise<SchemaMonitorStatus> {
  const { data } = await client.put<SchemaMonitorStatus>(
    `/api/subscriptions/${subscriptionId}/schema-monitor`,
    payload,
  );
  return data;
}

export async function pingSchemaMonitor(
  subscriptionId: number,
  payload?: {
    host?: string;
    port?: number;
    username?: string;
    password?: string;
  },
): Promise<SchemaMonitorPingResult> {
  const { data } = await client.post<SchemaMonitorPingResult>(
    `/api/subscriptions/${subscriptionId}/schema-ping`,
    payload ?? {},
  );
  return data;
}

export async function scanSchemaMonitor(subscriptionId: number): Promise<SchemaScanResult> {
  const { data } = await client.post<SchemaScanResult>(
    `/api/subscriptions/${subscriptionId}/schema-scan`,
    {},
    { timeout: 120000 },
  );
  return data;
}

export async function updateRepoAccessSettings(payload: {
  gitlab_base_url?: string;
  gitlab_token?: string;
  github_token?: string;
  public_webhook_base_url?: string;
}): Promise<RepoAccessSettings> {
  const { data } = await client.put<RepoAccessSettings>('/api/settings/repo-access', payload);
  return data;
}

export async function fetchApiMonitorFilterOptions(params?: {
  project?: number;
  environment?: number;
}) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorFilterOptions>(
    '/api/api-monitor/filter-options',
    { params },
  );
  return data;
}

export async function fetchApiMonitorServices(params?: {
  project?: number;
  environment?: number;
  name?: string;
}) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorService[]>(
    '/api/api-monitor/services',
    { params },
  );
  return data;
}

export async function fetchApiMonitorModules(serviceId: string) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorModules>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/modules`,
  );
  return data;
}

export async function fetchApiMonitorGroups(serviceId: string, module?: string) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorGroups>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/groups`,
    { params: module ? { module } : undefined },
  );
  return data;
}

export async function fetchApiMonitorGroupEndpoints(
  serviceId: string,
  tag: string,
  module?: string,
) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorGroupEndpoints>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/groups/${encodeURIComponent(tag)}/endpoints`,
    { params: module ? { module } : undefined },
  );
  return data;
}

export async function fetchApiMonitorEndpoint(serviceId: string, endpointId: string) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorEndpoint>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/endpoints/${encodeURIComponent(endpointId)}`,
  );
  return data;
}

export async function fetchApiMonitorProxy(payload: {
  method: string;
  url: string;
  headers?: Record<string, string>;
  body?: string;
}) {
  const { data } = await client.post<{
    status_code: number;
    headers: Record<string, string>;
    body: string;
    elapsed_ms: number;
  }>('/api/api-monitor/proxy', payload, { timeout: 60000 });
  return data;
}

export async function fetchApiMonitorSpec(serviceId: string, module?: string) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorSpec>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/spec`,
    { params: module ? { module } : undefined, timeout: 120000 },
  );
  return data;
}

export async function fetchApiMonitorScanRuns(serviceId: string, limit = 50) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorScanRun[]>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/scan-runs`,
    { params: { limit } },
  );
  return data;
}

export async function fetchApiMonitorScanRunChanges(serviceId: string, scanRunId: number) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorScanRunChanges>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/scan-runs/${scanRunId}/changes`,
  );
  return data;
}

export async function fetchApiMonitorEndpointChanges(
  serviceId: string,
  endpointId: string,
  limit = 50,
) {
  const { data } = await client.get<import('../types/apiMonitor').ApiMonitorEndpointChange[]>(
    `/api/api-monitor/services/${encodeURIComponent(serviceId)}/endpoints/${encodeURIComponent(endpointId)}/changes`,
    { params: { limit } },
  );
  return data;
}

export async function syncSubscriptionApi(subscriptionId: number, linkKey?: string) {
  const { data } = await client.post<{
    subscription_id: number;
    synced: number;
    skipped: number;
    failed: number;
    message: string;
  }>(
    `/api/subscriptions/${subscriptionId}/api-sync`,
    null,
    {
      params: linkKey ? { link_key: linkKey } : undefined,
      timeout: 300000,
    },
  );
  return data;
}

export async function fetchApiTestCases(params?: {
  project_id?: number;
  environment_id?: number;
  service?: string;
  endpoint_id?: string;
  keyword?: string;
  status?: string;
  page?: number;
  page_size?: number;
}) {
  const { data } = await client.get<import('../types/apiTestCase').ApiTestCaseList>(
    '/api/api-test-cases',
    { params },
  );
  return data;
}

export async function fetchApiTestCase(id: number) {
  const { data } = await client.get<import('../types/apiTestCase').ApiTestCase>(
    `/api/api-test-cases/${id}`,
  );
  return data;
}

export async function createApiTestCase(payload: import('../types/apiTestCase').ApiTestCaseFormValues) {
  const { data } = await client.post<import('../types/apiTestCase').ApiTestCase>(
    '/api/api-test-cases',
    payload,
  );
  return data;
}

export async function updateApiTestCase(
  id: number,
  payload: Partial<import('../types/apiTestCase').ApiTestCaseFormValues>,
) {
  const { data } = await client.put<import('../types/apiTestCase').ApiTestCase>(
    `/api/api-test-cases/${id}`,
    payload,
  );
  return data;
}

export async function deleteApiTestCase(id: number) {
  await client.delete(`/api/api-test-cases/${id}`);
}

export async function restoreApiTestCase(id: number) {
  const { data } = await client.post<import('../types/apiTestCase').ApiTestCase>(
    `/api/api-test-cases/${id}/restore`,
  );
  return data;
}

export async function generateApiTestCasesFromEndpoint(payload: {
  endpoint_id: string;
  project_id: number;
  environment_id: number;
  service: string;
  method: string;
  api_path: string;
  summary?: string;
  parameters?: import('../types/apiMonitor').ApiMonitorParameter[];
  expected_status?: number;
  expected_response?: string;
}) {
  const { data } = await client.post<{
    items: import('../types/apiTestCase').ApiTestCase[];
    created: number;
  }>('/api/api-test-cases/generate-from-endpoint', payload);
  return data;
}
