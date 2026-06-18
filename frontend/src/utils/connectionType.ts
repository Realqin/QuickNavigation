import type { Connection, DictItem } from '../types';
import { formatKafkaBrokersForInput } from './kafkaBrokers';

export type ConnectionKind = 'other' | 'database' | 'terminal' | 'redis' | 'mqtt' | 'kafka' | 'gitlab';

export const LABEL_OTHER = '其他';
export const LABEL_DATABASE = '数据库';
export const LABEL_TERMINAL = '终端模拟器';
export const LABEL_REDIS = 'Redis';
export const LABEL_MQTT = 'MQTT';
export const LABEL_KAFKA = 'Kafka';
export const LABEL_GITLAB = 'GitLab 仓库';

const KIND_BY_LABEL_NAME: Record<string, ConnectionKind> = {
  [LABEL_DATABASE]: 'database',
  [LABEL_TERMINAL]: 'terminal',
  [LABEL_REDIS]: 'redis',
  [LABEL_MQTT]: 'mqtt',
  [LABEL_KAFKA]: 'kafka',
  [LABEL_GITLAB]: 'gitlab',
};

export const DEFAULT_PORTS: Record<ConnectionKind, number | undefined> = {
  other: undefined,
  database: 3306,
  terminal: 22,
  redis: 6379,
  mqtt: 1883,
  kafka: 9092,
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

export function formatConnectionEndpoint(connection: Connection): string {
  if (connection.url?.startsWith('kafka://')) {
    return formatKafkaBrokersForInput(connection.host, connection.port);
  }
  if (connection.host) {
    const port = connection.port ? `:${connection.port}` : '';
    if (connection.database_name) {
      return `${connection.host}${port}/${connection.database_name}`;
    }
    if (connection.username) {
      return `${connection.username}@${connection.host}${port}`;
    }
    if (connection.url?.startsWith('mqtt://')) {
      return connection.url;
    }
    if (connection.mqtt_subscriptions?.length) {
      return `mqtt://${connection.host}${port} · ${connection.mqtt_subscriptions.length} 个订阅`;
    }
    return `mqtt://${connection.host}${port}`;
  }
  return connection.url;
}

export function supportsConnectionTest(kind: ConnectionKind): boolean {
  return kind !== 'other' && kind !== 'gitlab';
}
