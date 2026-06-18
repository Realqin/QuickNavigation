export type ConnectionMethodType =
  | 'methodDatabase'
  | 'methodTerminal'
  | 'methodRedis'
  | 'methodMqtt'
  | 'methodKafka';

export type PageType =
  | 'home'
  | 'connections'
  | 'logs'
  | 'dict'
  | 'apiMonitor'
  | 'apiCases'
  | 'llmConfigs'
  | 'prompts'
  | ConnectionMethodType;

export interface AppTab {
  key: PageType;
  type: PageType;
  label: string;
}

export const PAGE_LABELS: Record<PageType, string> = {
  home: '首页',
  connections: '连接管理',
  logs: '日志订阅',
  dict: '字典管理',
  apiMonitor: '接口监听',
  apiCases: '接口用例',
  llmConfigs: 'LLM配置',
  prompts: '提示词管理',
  methodDatabase: '数据库',
  methodTerminal: 'Linux 终端',
  methodRedis: 'Redis',
  methodMqtt: 'MQTT',
  methodKafka: 'Kafka',
};

export const CONNECTION_METHOD_MENU_KEY = 'connectionMethods';

export const CONFIG_MENU_KEY = 'configManagement';

export const CONFIG_PAGE_TYPES: PageType[] = ['llmConfigs', 'prompts', 'dict'];

export const CONNECTION_METHOD_TYPES: ConnectionMethodType[] = [
  'methodDatabase',
  'methodTerminal',
  'methodRedis',
  'methodMqtt',
  'methodKafka',
];

export function isConnectionMethodType(type: PageType): type is ConnectionMethodType {
  return CONNECTION_METHOD_TYPES.includes(type as ConnectionMethodType);
}

export function isConfigPageType(type: PageType): boolean {
  return CONFIG_PAGE_TYPES.includes(type);
}

export function createTab(type: PageType): AppTab {
  return {
    key: type,
    type,
    label: PAGE_LABELS[type],
  };
}
