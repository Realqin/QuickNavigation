export type PageType = 'home' | 'connections' | 'logs' | 'dict';

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
};

export function createTab(type: PageType): AppTab {
  return {
    key: type,
    type,
    label: PAGE_LABELS[type],
  };
}
