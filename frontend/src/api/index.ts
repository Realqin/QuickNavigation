import axios from 'axios';
import { resolveApiBaseUrl } from '../utils/apiBase';
import { buildLogsWebSocketUrl } from '../utils/appWebSocket';
import {
  getCachedDictItems,
  getInflightDictRequest,
  invalidateDictCache,
  setCachedDictItems,
  trackInflightDictRequest,
} from '../utils/dictCache';
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
  SchemaResetBaselineResult,
  SchemaScanResult,
} from '../types';
import type {
  K8sClusterConfig,
  K8sClusterFormValues,
  K8sConnectResult,
  K8sPodLogResult,
  K8sProject,
  K8sScalePayload,
  K8sScaleResult,
  K8sService,
  K8sWatermarkResult,
  K8sAlarmMonitorGroup,
  K8sAlarmMonitorService,
  K8sAlarmMonitorSyncResult,
  K8sAlarmEvent,
  K8sRestartMonitorOption,
} from '../types/k8s';
import { coalesceGet } from '../utils/getCoalesce';
import { acquireHttpSlot, releaseHttpSlot } from '../utils/httpQueue';

export { getApiErrorMessage, showApiError } from '../utils/apiError';

const HTTP_QUEUED = Symbol('httpQueued');

const client = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 15000,
});

client.interceptors.request.use(async (config) => {
  await acquireHttpSlot();
  (config as typeof config & { [HTTP_QUEUED]?: boolean })[HTTP_QUEUED] = true;
  const token = localStorage.getItem('qn_access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function releaseIfQueued(config: unknown): void {
  if (config && typeof config === 'object' && (config as { [HTTP_QUEUED]?: boolean })[HTTP_QUEUED]) {
    releaseHttpSlot();
  }
}

client.interceptors.response.use(
  (response) => {
    releaseIfQueued(response.config);
    return response;
  },
  (error) => {
    releaseIfQueued(error?.config);
    const status = error?.response?.status;
    const url = String(error?.config?.url || '');
    if (status === 401 && !url.includes('/api/auth/login')) {
      localStorage.removeItem('qn_access_token');
      localStorage.removeItem('qn_user');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export async function fetchHome(project: number, environment: number): Promise<HomeData> {
  return coalesceGet('/api/connections/home', { project, environment }, async () => {
    const { data } = await client.get<HomeData>('/api/connections/home', {
      params: { project, environment },
    });
    return data;
  });
}

export const FILTER_EMPTY = 0;

export async function fetchK8sClusters(): Promise<K8sClusterConfig[]> {
  const { data } = await client.get<K8sClusterConfig[]>('/api/k8s/clusters');
  return data;
}

export async function createK8sCluster(
  values: K8sClusterFormValues,
): Promise<K8sClusterConfig> {
  const { data } = await client.post<K8sClusterConfig>('/api/k8s/clusters', values);
  return data;
}

export async function updateK8sCluster(
  id: number,
  values: Partial<K8sClusterFormValues>,
): Promise<K8sClusterConfig> {
  const { data } = await client.put<K8sClusterConfig>(`/api/k8s/clusters/${id}`, values);
  return data;
}

export async function deleteK8sCluster(id: number): Promise<void> {
  await client.delete(`/api/k8s/clusters/${id}`);
}

export async function connectK8sCluster(id: number): Promise<K8sConnectResult> {
  const { data } = await client.post<K8sConnectResult>(`/api/k8s/clusters/${id}/connect`, null, {
    timeout: 45000,
  });
  return data;
}

export async function fetchK8sProjects(clusterId: number): Promise<K8sProject[]> {
  const { data } = await client.get<K8sProject[]>(`/api/k8s/clusters/${clusterId}/projects`, {
    timeout: 45000,
  });
  return data;
}

export async function fetchK8sServices(
  clusterId: number,
  project: string,
): Promise<K8sService[]> {
  const { data } = await client.get<K8sService[]>(`/api/k8s/clusters/${clusterId}/services`, {
    params: { project },
    timeout: 60000,
  });
  return data;
}

export async function scaleK8sService(
  clusterId: number,
  payload: K8sScalePayload,
): Promise<K8sScaleResult> {
  const { data } = await client.post<K8sScaleResult>(
    `/api/k8s/clusters/${clusterId}/scale`,
    payload,
    { timeout: 45000 },
  );
  return data;
}

export async function fetchK8sPodLogs(params: {
  clusterId: number;
  namespace: string;
  podName: string;
  container?: string;
  tailLines?: number;
}): Promise<K8sPodLogResult> {
  const { data } = await client.get<K8sPodLogResult>(
    `/api/k8s/clusters/${params.clusterId}/logs`,
    {
      params: {
        namespace: params.namespace,
        pod_name: params.podName,
        container: params.container || undefined,
        tail_lines: params.tailLines ?? 500,
      },
      timeout: 60000,
    },
  );
  return data;
}

export async function fetchK8sWatermarks(params: {
  clusterId: number;
  namespace: string;
  serviceName: string;
  port: number;
}): Promise<K8sWatermarkResult> {
  const { data } = await client.get<K8sWatermarkResult>(
    `/api/k8s/clusters/${params.clusterId}/watermarks`,
    {
      params: {
        namespace: params.namespace,
        service_name: params.serviceName,
        port: params.port,
      },
      timeout: 60000,
    },
  );
  return data;
}

export async function syncK8sAlarmMonitor(clusterId: number): Promise<K8sAlarmMonitorSyncResult> {
  const { data } = await client.post<K8sAlarmMonitorSyncResult>(
    `/api/k8s/clusters/${clusterId}/alarm-monitor/sync`,
    null,
    { timeout: 120000 },
  );
  return data;
}

export async function syncK8sAlarmMonitorGroup(
  clusterId: number,
  namespace: string,
): Promise<K8sAlarmMonitorSyncResult> {
  const { data } = await client.post<K8sAlarmMonitorSyncResult>(
    `/api/k8s/clusters/${clusterId}/alarm-monitor/groups/${encodeURIComponent(namespace)}/sync`,
    null,
    { timeout: 300000 },
  );
  return data;
}

export async function fetchK8sAlarmMonitorGroups(clusterId: number): Promise<K8sAlarmMonitorGroup[]> {
  const { data } = await client.get<K8sAlarmMonitorGroup[]>(
    `/api/k8s/clusters/${clusterId}/alarm-monitor/groups`,
    { timeout: 60000 },
  );
  return data;
}

export async function updateK8sAlarmMonitorGroup(
  clusterId: number,
  namespace: string,
  enabled: boolean,
): Promise<K8sAlarmMonitorGroup> {
  const { data } = await client.put<K8sAlarmMonitorGroup>(
    `/api/k8s/clusters/${clusterId}/alarm-monitor/groups/${encodeURIComponent(namespace)}`,
    { enabled },
  );
  return data;
}

export async function fetchK8sAlarmMonitorServices(
  clusterId: number,
  namespace: string,
): Promise<K8sAlarmMonitorService[]> {
  const { data } = await client.get<K8sAlarmMonitorService[]>(
    `/api/k8s/clusters/${clusterId}/alarm-monitor/groups/${encodeURIComponent(namespace)}/services`,
  );
  return data;
}

export async function resolveConnectionK8sAlarmCluster(
  connectionId: number,
): Promise<{ cluster_id: number; cluster_name: string }> {
  const { data } = await client.get<{ cluster_id: number; cluster_name: string }>(
    `/api/connections/${connectionId}/k8s-alarm-cluster`,
  );
  return data;
}

export async function saveK8sAlarmMonitorService(
  clusterId: number,
  namespace: string,
  serviceName: string,
  payload: {
    restart_monitor: K8sRestartMonitorOption;
    watermark_minutes: number | null;
  },
): Promise<K8sAlarmMonitorService> {
  const { data } = await client.put<K8sAlarmMonitorService>(
    `/api/k8s/clusters/${clusterId}/alarm-monitor/groups/${encodeURIComponent(namespace)}/services/${encodeURIComponent(serviceName)}`,
    payload,
  );
  return data;
}

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
  return coalesceGet('/api/logs', params, async () => {
    const { data } = await client.get<ActivityLog[]>('/api/logs', { params });
    return data;
  });
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
  return coalesceGet('/api/subscriptions', params, async () => {
    const { data } = await client.get<GitlabSubscriptionTree[]>('/api/subscriptions', { params });
    return data;
  });
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

export interface NotifyWebSocketHandle {
  close: () => void;
  updateSubscription?: (options?: { project?: number | null; environment?: number | null }) => void;
}

const NOTIFY_WS_RECONNECT_MS = 3000;

export function createLogsWebSocket(
  onMessage: (log: ActivityLog) => void,
  options?: { project?: number | null; environment?: number | null },
): NotifyWebSocketHandle {
  return createNotifyWebSocket({ onLog: onMessage }, options);
}

export function createNotifyWebSocket(
  handlers: {
    onLog?: (log: ActivityLog) => void;
    onK8sAlarm?: (event: K8sAlarmEvent) => void;
  },
  options?: { project?: number | null; environment?: number | null },
): NotifyWebSocketHandle {
  let ws: WebSocket | null = null;
  let disposed = false;
  let reconnectTimer: number | undefined;
  let subscribeOptions = options;

  const sendSubscribe = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    const project = subscribeOptions?.project;
    const environment = subscribeOptions?.environment;
    if (project == null || environment == null) {
      return;
    }
    ws.send(
      JSON.stringify({
        type: 'subscribe',
        project,
        environment,
      }),
    );
  };

  const dispatch = (event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data as string);
      if (msg.type === 'log:new' && msg.data && handlers.onLog) {
        handlers.onLog(msg.data as ActivityLog);
      }
      if (msg.type === 'k8s-alarm:new' && msg.data && handlers.onK8sAlarm) {
        handlers.onK8sAlarm(msg.data as K8sAlarmEvent);
      }
    } catch {
      // ignore malformed messages
    }
  };

  const connect = () => {
    if (disposed || document.hidden) {
      return;
    }
    ws = new WebSocket(buildLogsWebSocketUrl());
    ws.onopen = () => {
      sendSubscribe();
    };
    ws.onmessage = dispatch;
    ws.onclose = () => {
      ws = null;
      if (!disposed && !document.hidden) {
        reconnectTimer = window.setTimeout(connect, NOTIFY_WS_RECONNECT_MS);
      }
    };
    ws.onerror = () => {
      ws?.close();
    };
  };

  const onVisibilityChange = () => {
    if (document.hidden) {
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
      }
      ws?.close();
      ws = null;
      return;
    }
    if (!disposed) {
      connect();
    }
  };

  document.addEventListener('visibilitychange', onVisibilityChange);
  connect();

  return {
    close: () => {
      disposed = true;
      document.removeEventListener('visibilitychange', onVisibilityChange);
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      ws?.close();
      ws = null;
    },
    updateSubscription(next?: { project?: number | null; environment?: number | null }) {
      subscribeOptions = next;
      sendSubscribe();
    },
  };
}

export async function fetchK8sAlarmEvents(
  clusterId: number,
  params?: { status?: string; limit?: number },
): Promise<K8sAlarmEvent[]> {
  const { data } = await client.get<K8sAlarmEvent[]>(
    `/api/k8s/clusters/${clusterId}/alarm-events`,
    { params },
  );
  return data;
}

export async function fetchK8sAlarmUnreadCount(clusterId: number): Promise<number> {
  const { data } = await client.get<{ count: number }>(
    `/api/k8s/clusters/${clusterId}/alarm-events/unread-count`,
  );
  return data.count;
}

export async function markK8sAlarmEventRead(eventId: number): Promise<K8sAlarmEvent> {
  const { data } = await client.patch<K8sAlarmEvent>(`/api/k8s/alarm-events/${eventId}/read`);
  return data;
}

export async function markK8sAlarmEventsReadAll(clusterId: number): Promise<number> {
  const { data } = await client.post<{ updated: number }>(
    `/api/k8s/clusters/${clusterId}/alarm-events/read-all`,
  );
  return data.updated;
}

export async function fetchDictItems(
  type?: DictType,
  options?: { force?: boolean },
): Promise<DictItem[]> {
  const force = options?.force ?? false;
  if (!force) {
    const cached = getCachedDictItems(type);
    if (cached) {
      return cached;
    }
    const pending = getInflightDictRequest(type);
    if (pending) {
      return pending;
    }
  }

  const request = client
    .get<DictItem[]>('/api/dict', { params: type ? { type } : {} })
    .then(({ data }) => {
      setCachedDictItems(type, data);
      return data;
    });

  if (!force) {
    trackInflightDictRequest(type, request);
  }

  return request;
}

export async function createDictItem(payload: DictFormValues): Promise<DictItem> {
  const { data } = await client.post<DictItem>('/api/dict', payload);
  invalidateDictCache(payload.type);
  invalidateDictCache();
  return data;
}

export async function updateDictItem(
  id: number,
  payload: Partial<DictFormValues>,
): Promise<DictItem> {
  const { data } = await client.patch<DictItem>(`/api/dict/${id}`, payload);
  if (payload.type) {
    invalidateDictCache(payload.type);
  } else {
    invalidateDictCache();
  }
  return data;
}

export async function deleteDictItem(id: number): Promise<void> {
  await client.delete(`/api/dict/${id}`);
  invalidateDictCache();
}

export async function fetchPublicConfig(): Promise<PublicConfig> {
  return coalesceGet('/api/public/config', undefined, async () => {
    const { data } = await client.get<PublicConfig>('/api/public/config');
    return data;
  });
}

export async function fetchOmnidbMenuUrl(): Promise<{ url: string }> {
  const { data } = await client.get<{ url: string }>('/api/public/omnidb-menu-url');
  return data;
}

export async function fetchRedisinsightMenuUrl(): Promise<{ url: string }> {
  const { data } = await client.get<{ url: string }>('/api/public/redisinsight-menu-url');
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

export async function resetSchemaMonitorBaseline(
  subscriptionId: number,
): Promise<SchemaResetBaselineResult> {
  const { data } = await client.post<SchemaResetBaselineResult>(
    `/api/subscriptions/${subscriptionId}/schema-reset-baseline`,
    {},
    { timeout: 120000 },
  );
  return data;
}

export async function updateRepoAccessSettings(payload: {
  gitlab_base_url?: string;
  gitlab_token?: string;
  gitlab_ssh_private_key?: string;
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
  return coalesceGet('/api/api-monitor/filter-options', params, async () => {
    const { data } = await client.get<import('../types/apiMonitor').ApiMonitorFilterOptions>(
      '/api/api-monitor/filter-options',
      { params },
    );
    return data;
  });
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

export async function saveApiTestCaseExecutionResult(
  id: number,
  payload: {
    passed: boolean;
    status_code?: number | null;
    response?: string | null;
    detail?: string | null;
  },
) {
  const { data } = await client.post<import('../types/apiTestCase').ApiTestCase>(
    `/api/api-test-cases/${id}/execution-result`,
    payload,
  );
  return data;
}

export async function deleteApiTestCase(id: number) {
  await client.delete(`/api/api-test-cases/${id}`);
}

export async function permanentDeleteApiTestCase(id: number) {
  await client.delete(`/api/api-test-cases/${id}/permanent`);
}

export async function batchDeleteApiTestCases(ids: number[]) {
  const { data } = await client.post<{
    soft_deleted: number;
    hard_deleted: number;
    not_found: number;
    total: number;
  }>('/api/api-test-cases/batch-delete', { ids });
  return data;
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
  overwrite?: boolean;
}) {
  const { data } = await client.post<{
    items: import('../types/apiTestCase').ApiTestCase[];
    created: number;
    overwritten?: number;
  }>('/api/api-test-cases/generate-from-endpoint', payload, { timeout: 180000 });
  return data;
}

export async function fetchAiAnalysis(payload: {
  log_id?: number;
  scenario?: string;
  title?: string;
  summary?: string;
  context?: string;
  content?: string;
  content_label?: string;
  prompt_type?: string;
  extra?: Record<string, unknown>;
}) {
  const { data } = await client.post<import('../types/aiAnalysis').AiAnalysisResult>(
    '/api/ai-analysis',
    payload,
    { timeout: 180000 },
  );
  return data;
}

export async function fetchLlmConfigs() {
  const { data } = await client.get<import('../types/llm').LlmConfig[]>('/api/llm-configs');
  return data;
}

export async function createLlmConfig(payload: import('../types/llm').LlmConfigFormValues) {
  const { data } = await client.post<import('../types/llm').LlmConfig>('/api/llm-configs', payload);
  return data;
}

export async function updateLlmConfig(id: string, payload: import('../types/llm').LlmConfigFormValues) {
  const { data } = await client.put<import('../types/llm').LlmConfig>(`/api/llm-configs/${id}`, payload);
  return data;
}

export async function toggleLlmConfig(id: string, enabled: boolean) {
  const { data } = await client.post<import('../types/llm').LlmConfig>(`/api/llm-configs/${id}/toggle`, {
    enabled,
  });
  return data;
}

export async function deleteLlmConfig(id: string) {
  await client.delete(`/api/llm-configs/${id}`);
}

export async function testLlmConnection(payload: import('../types/llm').LlmConnectionTestPayload) {
  const { data } = await client.post<{ ok: boolean; message: string; model?: string }>(
    '/api/llm-configs/test-connection',
    payload,
    { timeout: 45000 },
  );
  return data;
}

export async function fetchLlmModels(payload: import('../types/llm').LlmModelsPayload) {
  const { data } = await client.post<{ items: string[] }>('/api/llm-configs/models', payload, {
    timeout: 90000,
  });
  return data;
}

export async function fetchPromptTemplates() {
  const { data } = await client.get<import('../types/prompt').PromptTemplate[]>('/api/prompts');
  return data;
}

export async function createPromptTemplate(payload: import('../types/prompt').PromptTemplateFormValues) {
  const { data } = await client.post<import('../types/prompt').PromptTemplate>('/api/prompts', payload);
  return data;
}

export async function updatePromptTemplate(
  id: string,
  payload: import('../types/prompt').PromptTemplateFormValues,
) {
  const { data } = await client.put<import('../types/prompt').PromptTemplate>(`/api/prompts/${id}`, payload);
  return data;
}

export async function togglePromptTemplate(id: string, enabled: boolean) {
  const { data } = await client.post<import('../types/prompt').PromptTemplate>(`/api/prompts/${id}/toggle`, {
    enabled,
  });
  return data;
}

export async function deletePromptTemplate(id: string) {
  await client.delete(`/api/prompts/${id}`);
}

export async function login(username: string, password: string) {
  const { data } = await client.post<import('../types/auth').AuthLoginResult>('/api/auth/login', {
    username,
    password,
  });
  return data;
}

export async function logout() {
  await client.post('/api/auth/logout');
}

export async function fetchAuthMe() {
  const { data } = await client.get<{ user: import('../types/auth').UserInfo }>('/api/auth/me');
  return data.user;
}

export async function fetchMenuPermissions() {
  const { data } = await client.get<import('../types/auth').MenuPermissionNode[]>(
    '/api/menu-permissions',
  );
  return data;
}

export async function fetchUsers() {
  const { data } = await client.get<import('../types/auth').UserInfo[]>('/api/users');
  return data;
}

export async function createUser(payload: import('../types/auth').UserFormValues) {
  const { data } = await client.post<import('../types/auth').UserInfo>('/api/users', payload);
  return data;
}

export async function updateUser(
  id: number,
  payload: Partial<import('../types/auth').UserFormValues>,
) {
  const { data } = await client.put<import('../types/auth').UserInfo>(`/api/users/${id}`, payload);
  return data;
}

export async function deleteUser(id: number) {
  await client.delete(`/api/users/${id}`);
}

export async function fetchOperationLogs(params?: {
  keyword?: string;
  action?: string;
  username?: string;
  limit?: number;
  offset?: number;
}) {
  const { data } = await client.get<{
    items: import('../types/auth').OperationLogItem[];
    total: number;
  }>('/api/operation-logs', { params });
  return data;
}

export async function reportPageOpen(menuKey: string) {
  await client.post('/api/operation-logs/report', {
    action: 'open',
    menu_key: menuKey,
    content: '',
  });
}
