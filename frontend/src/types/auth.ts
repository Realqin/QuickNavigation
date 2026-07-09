export interface MenuPermissionNode {
  key: string;
  title: string;
  children?: MenuPermissionNode[];
}

export interface UserInfo {
  id: number;
  username: string;
  nickname: string;
  password?: string;
  menu_permissions: string[];
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthLoginResult {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export interface UserFormValues {
  username: string;
  nickname: string;
  password?: string;
  menu_permissions: string[];
  is_admin: boolean;
  is_active: boolean;
}

export interface OperationLogItem {
  id: number;
  user_id: number | null;
  username: string;
  action: string;
  action_label: string;
  resource_type?: string | null;
  resource_id?: string | null;
  content: string;
  ip_address?: string | null;
  created_at: string;
}

export const MENU_PERMISSION_TREE: MenuPermissionNode[] = [
  { key: 'home', title: '首页' },
  { key: 'logs', title: '日志订阅' },
  { key: 'apiMonitor', title: '接口调试' },
  { key: 'serviceMonitor', title: 'K8s连接（K8s）' },
  { key: 'connections', title: '连接管理' },
  { key: 'apiCases', title: '接口用例管理' },
  {
    key: 'configManagement',
    title: '配置管理',
    children: [
      { key: 'llmConfigs', title: 'LLM配置' },
      { key: 'prompts', title: '提示词管理' },
      { key: 'dict', title: '字典管理' },
      { key: 'userManagement', title: '用户管理' },
    ],
  },
  {
    key: 'connectionMethods',
    title: '连接方式 / 连接管理',
    children: [
      { key: 'methodDatabase', title: 'MySQL/数据库' },
      { key: 'methodTerminal', title: '终端模拟器' },
      { key: 'methodRedis', title: 'Redis' },
      { key: 'methodMqtt', title: 'MQTT' },
      { key: 'methodKafka', title: 'Kafka' },
    ],
  },
  { key: 'operationLogs', title: '操作日志' },
];

export const ALL_MENU_PERMISSION_KEYS: string[] = [
  'home',
  'logs',
  'apiMonitor',
  'serviceMonitor',
  'connections',
  'apiCases',
  'llmConfigs',
  'prompts',
  'dict',
  'methodDatabase',
  'methodTerminal',
  'methodRedis',
  'methodMqtt',
  'methodKafka',
  'userManagement',
  'operationLogs',
];

export function hasMenuPermission(user: UserInfo | null | undefined, menuKey: string): boolean {
  if (!user) return false;
  if (user.is_admin) return true;
  return user.menu_permissions.includes(menuKey);
}

export function collectPermissionLeafKeys(nodes: MenuPermissionNode[]): string[] {
  const keys: string[] = [];
  for (const node of nodes) {
    if (node.children?.length) {
      keys.push(...collectPermissionLeafKeys(node.children));
    } else {
      keys.push(node.key);
    }
  }
  return keys;
}
