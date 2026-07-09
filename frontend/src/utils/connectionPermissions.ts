import type { Connection, DictItem } from '../types';
import type { UserInfo } from '../types/auth';
import { resolveConnectionKind, type ConnectionKind } from './connectionType';

/** 需要按菜单权限管控的连接类型 */
const PERMISSION_CONTROLLED_KINDS: ConnectionKind[] = [
  'k8s',
  'database',
  'redis',
  'mqtt',
  'terminal',
  'kafka',
];

/** 不受连接类型权限管控 */
const UNCONTROLLED_KINDS: ConnectionKind[] = ['gitlab', 'other'];

export const CONNECTION_KIND_MENU: Record<
  (typeof PERMISSION_CONTROLLED_KINDS)[number],
  string
> = {
  k8s: 'serviceMonitor',
  database: 'methodDatabase',
  redis: 'methodRedis',
  mqtt: 'methodMqtt',
  terminal: 'methodTerminal',
  kafka: 'methodKafka',
};

export const CONNECTION_KIND_LABELS: Record<ConnectionKind, string> = {
  k8s: 'K8s',
  database: 'MySQL/数据库',
  redis: 'Redis',
  mqtt: 'MQTT',
  terminal: '终端模拟器',
  gitlab: 'GitLab',
  kafka: 'Kafka',
  other: '其他',
};

export function userCanAccessConnectionKind(
  user: UserInfo | null | undefined,
  kind: ConnectionKind,
): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  if (UNCONTROLLED_KINDS.includes(kind)) return true;
  if (!PERMISSION_CONTROLLED_KINDS.includes(kind)) return true;
  const menuKey = CONNECTION_KIND_MENU[kind as (typeof PERMISSION_CONTROLLED_KINDS)[number]];
  return user.menu_permissions.includes(menuKey);
}

export function hasAnyConnectionTypePermission(user: UserInfo | null | undefined): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  const permissions = new Set(user.menu_permissions);
  return PERMISSION_CONTROLLED_KINDS.some((kind) => permissions.has(CONNECTION_KIND_MENU[kind]));
}

export function canAccessConnectionsPage(user: UserInfo | null | undefined): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  return user.menu_permissions.includes('connections') || hasAnyConnectionTypePermission(user);
}

export function filterConnectionsByPermission(
  user: UserInfo | null | undefined,
  connections: Connection[],
  labelItems: DictItem[],
): Connection[] {
  if (!user || user.is_admin) return connections;
  return connections.filter((connection) =>
    userCanAccessConnectionKind(user, resolveConnectionKind(connection.type, labelItems)),
  );
}

export function filterLabelOptionsByPermission(
  user: UserInfo | null | undefined,
  labelOptions: Array<{ label: string; value: number }>,
  labelItems: DictItem[],
): Array<{ label: string; value: number }> {
  if (!user || user.is_admin) return labelOptions;
  return labelOptions.filter((option) =>
    userCanAccessConnectionKind(user, resolveConnectionKind(option.value, labelItems)),
  );
}
