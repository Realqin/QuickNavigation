import axios from 'axios';
import type {
  ActivityLog,
  ActivityLogDiff,
  Connection,
  ConnectionFormValues,
  DictFormValues,
  DictItem,
  DictType,
  HomeData,
  GitlabSubscriptionTree,
  PublicConfig,
  RepoAccessSettings,
  SchemaMonitorPingResult,
  SchemaMonitorStatus,
  SchemaScanResult,
} from '../types';

const client = axios.create({
  baseURL: '/',
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
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);
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
