import type { Connection, DictItem } from '../types';
import { formatKafkaBrokersForInput } from './kafkaBrokers';

export type ConnectionKind = 'other' | 'database' | 'terminal' | 'redis' | 'mqtt' | 'kafka' | 'gitlab' | 'k8s';

export const LABEL_OTHER = '其他';
export const LABEL_DATABASE = '数据库';
export const LABEL_TERMINAL = '终端模拟器';
export const LABEL_REDIS = 'Redis';
export const LABEL_MQTT = 'MQTT';
export const LABEL_KAFKA = 'Kafka';
export const LABEL_K8S = 'K8s';
export const LABEL_GITLAB = 'GitLab 仓库';

const KIND_BY_LABEL_NAME: Record<string, ConnectionKind> = {
  [LABEL_DATABASE]: 'database',
  [LABEL_TERMINAL]: 'terminal',
  [LABEL_REDIS]: 'redis',
  [LABEL_MQTT]: 'mqtt',
  [LABEL_KAFKA]: 'kafka',
  [LABEL_K8S]: 'k8s',
  [LABEL_GITLAB]: 'gitlab',
};

export const DEFAULT_PORTS: Record<ConnectionKind, number | undefined> = {
  other: undefined,
  database: 3306,
  terminal: 22,
  redis: 6379,
  mqtt: 1883,
  kafka: 9092,
  k8s: undefined,
  gitlab: undefined,
};

export function resolveConnectionKind(
  typeId: number | undefined,
  items: DictItem[],
): ConnectionKind {
  const item = items.find((entry) => entry.id === typeId);
  if (!item) return 'other';
  const mapped = KIND_BY_LABEL_NAME[item.name];
  if (mapped) return mapped;
  if (item.name.toLowerCase().includes('gitlab')) return 'gitlab';
  return 'other';
}

function buildAuthUri(
  scheme: string,
  connection: Connection,
  options?: { database?: boolean; suffix?: string },
): string {
  const host = connection.host?.trim();
  if (!host) {
    return (connection.url || '').trim();
  }
  const port = connection.port ? `:${connection.port}` : '';
  const user = connection.username?.trim();
  const auth = user ? `${user}@` : '';
  const db =
    options?.database && connection.database_name?.trim()
      ? `/${connection.database_name.trim()}`
      : '';
  const suffix = options?.suffix ?? '';
  return `${scheme}://${auth}${host}${port}${db}${suffix}`;
}

/** 卡片/列表展示用（含账号前缀）；点击跳转请用 getConnectionOpenUrl */
export function formatConnectionEndpoint(connection: Connection): string {
  const url = (connection.url || '').trim();

  if (url.startsWith('kafka://')) {
    const brokers = formatKafkaBrokersForInput(connection.host, connection.port);
    const user = connection.username?.trim();
    if (user) {
      return `kafka://${user}@${brokers}`;
    }
    return brokers;
  }

  const schemeFromUrl = url.match(/^(mysql|redis|mqtt|ssh):\/\//)?.[1];
  if (schemeFromUrl) {
    if (schemeFromUrl === 'mqtt' && connection.mqtt_subscriptions?.length) {
      return buildAuthUri('mqtt', connection, {
        suffix: ` · ${connection.mqtt_subscriptions.length} 个订阅`,
      });
    }
    return buildAuthUri(schemeFromUrl, connection, { database: schemeFromUrl === 'mysql' });
  }

  if (url.startsWith('ssh://')) {
    const user = connection.username?.trim();
    if (user && !url.includes('@')) {
      return buildAuthUri('ssh', connection);
    }
    return url;
  }

  if (url.startsWith('https://') || url.startsWith('http://')) {
    // K8s 等：库存原始访问地址，展示与跳转均用 url；IP/端口由后端按需解析
    return url;
  }

  if (connection.host) {
    const port = connection.port ? `:${connection.port}` : '';
    if (connection.database_name) {
      return buildAuthUri('mysql', connection, { database: true });
    }
    if (connection.username?.trim()) {
      return `${connection.username.trim()}@${connection.host}${port}`;
    }
    if (connection.mqtt_subscriptions?.length) {
      return buildAuthUri('mqtt', connection, {
        suffix: ` · ${connection.mqtt_subscriptions.length} 个订阅`,
      });
    }
    return `${connection.host}${port}`;
  }

  return url;
}

/** 实际打开/跳转用的 URL（保留原始访问地址，如 K8s 控制台 http 链接） */
export function getConnectionOpenUrl(connection: Connection): string {
  return (connection.url || '').trim() || formatConnectionEndpoint(connection);
}

export function supportsConnectionTest(kind: ConnectionKind): boolean {
  return kind !== 'other' && kind !== 'gitlab';
}
