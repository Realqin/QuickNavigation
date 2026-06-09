export interface SubLink {
  name: string;
  url: string;
  is_reachable?: boolean | null;
  last_checked_at?: string | null;
}

export type DictType = 'project' | 'environment' | 'label';

export interface DictItem {
  id: number;
  type: DictType;
  name: string;
  description?: string | null;
  sort_order: number;
  created_at?: string;
  updated_at?: string;
}

export interface Connection {
  id: number;
  name: string;
  url: string;
  description?: string | null;
  projects: number[];
  environments: number[];
  type: number;
  is_shared: boolean;
  sort_order: number;
  icon?: string | null;
  is_reachable?: boolean | null;
  last_checked_at?: string | null;
  sub_links: SubLink[];
  created_at: string;
  updated_at: string;
}

export interface ConnectionPingResult {
  id: number;
  is_reachable: boolean;
  last_checked_at: string;
}

export interface HomeData {
  shared: Connection[];
  scoped: Connection[];
  projects: DictItem[];
  environments: DictItem[];
  labels: DictItem[];
}

export interface ActivityLog {
  id: number;
  subscription_id?: number | null;
  connection_id?: number | null;
  project: string;
  environment: string;
  source_type: string;
  title: string;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
  author?: string | null;
  occurred_at: string;
  is_read: boolean;
}

export interface Subscription {
  id: number;
  connection_id: number;
  enabled: boolean;
  github_repo?: string | null;
  github_events?: string[] | null;
  db_filter?: Record<string, unknown> | null;
  notify_homepage: boolean;
  webhook_secret: string;
  webhook_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionFormValues {
  name: string;
  url: string;
  description?: string;
  projects: number[];
  environments: number[];
  type: number;
  is_shared: boolean;
  sub_links?: SubLink[];
}

export interface DictFormValues {
  type: DictType;
  name: string;
  description?: string;
  sort_order: number;
}

export const DICT_TYPE_LABELS: Record<DictType, string> = {
  project: '项目',
  environment: '环境',
  label: '类型',
};
