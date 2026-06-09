import axios from 'axios';
import type {
  ActivityLog,
  Connection,
  ConnectionFormValues,
  DictFormValues,
  DictItem,
  DictType,
  HomeData,
  Subscription,
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

export async function fetchConnections(params?: {
  name?: string;
  project?: number;
  environment?: number;
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

export async function fetchSubscriptions(): Promise<Subscription[]> {
  const { data } = await client.get<Subscription[]>('/api/subscriptions');
  return data;
}

export async function createSubscription(payload: {
  connection_id: number;
  enabled?: boolean;
  github_repo?: string;
  github_events?: string[];
  notify_homepage?: boolean;
}): Promise<Subscription> {
  const { data } = await client.post<Subscription>('/api/subscriptions', payload);
  return data;
}

export async function updateSubscription(
  id: number,
  payload: Partial<{
    enabled: boolean;
    github_repo: string;
    github_events: string[];
    notify_homepage: boolean;
  }>,
): Promise<Subscription> {
  const { data } = await client.patch<Subscription>(`/api/subscriptions/${id}`, payload);
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
