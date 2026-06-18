export interface ApiMonitorParameter {
  name: string;
  in: string;
  required: boolean;
  data_type: string;
  description?: string;
  schema_name?: string | null;
  children?: ApiMonitorParameter[];
}

export interface ApiMonitorResponse {
  status_code: string;
  description?: string;
  data_type?: string;
  schema_name?: string | null;
  properties?: ApiMonitorParameter[];
}

export interface ApiMonitorEndpoint {
  id: string;
  method: string;
  path: string;
  summary: string;
  tags: string[];
  request_content_type: string;
  response_content_type: string;
  parameters: ApiMonitorParameter[];
  responses: ApiMonitorResponse[];
  source: {
    file?: string;
    line?: number;
    symbol?: string;
    author?: string | null;
    authored_at?: string | null;
  };
}

export interface ApiMonitorGroup {
  tag: string;
  endpoints: ApiMonitorEndpoint[];
}

export interface ApiMonitorSpec {
  spec_version: number;
  meta: Record<string, unknown>;
  groups: ApiMonitorGroup[];
  endpoints: ApiMonitorEndpoint[];
  endpoint_count: number;
}

export interface ApiMonitorService {
  id: string;
  connection_id: number;
  subscription_id?: number | null;
  link_key: string;
  name: string;
  connection_name: string;
  repo_path: string;
  branch?: string | null;
  provider?: string | null;
  projects: number[];
  environments: number[];
  project_display: string;
  environment_display: string;
  connection_type_name?: string | null;
  endpoint_count: number;
  last_scan_at?: string | null;
  scan_status?: string | null;
  has_snapshot: boolean;
}

export interface ApiMonitorFilterOptions {
  projects: Array<{ id: number; name: string }>;
  environments: Array<{ id: number; name: string }>;
  names: Array<{ id: string; label: string }>;
}

export interface ApiMonitorModuleSummary {
  name: string;
  endpoint_count: number;
}

export interface ApiMonitorModules {
  service_id: string;
  modules: ApiMonitorModuleSummary[];
}

export interface ApiMonitorGroupSummary {
  tag: string;
  endpoint_count: number;
}

export interface ApiMonitorGroups {
  service_id: string;
  module?: string | null;
  display_name: string;
  endpoint_count: number;
  has_snapshot: boolean;
  scan_status?: string | null;
  repo_path: string;
  branch?: string | null;
  project_display: string;
  environment_display: string;
  groups: ApiMonitorGroupSummary[];
  removed_endpoint_keys?: string[];
}

export interface ApiMonitorEndpointSummary {
  id: string;
  method: string;
  path: string;
  summary: string;
}

export interface ApiMonitorGroupEndpoints {
  tag: string;
  endpoints: ApiMonitorEndpointSummary[];
}

export type ApiMonitorDetailTab = 'doc' | 'cases' | 'debug' | 'changes';

export interface ApiMonitorScanRun {
  id: number;
  subscription_id: number;
  link_key: string;
  commit_sha?: string | null;
  commit_message?: string | null;
  branch?: string | null;
  is_baseline: boolean;
  endpoint_count_before: number;
  endpoint_count_after: number;
  added_count: number;
  modified_count: number;
  removed_count: number;
  scanned_at: string;
}

export interface ApiMonitorEndpointChange {
  id: number;
  scan_run_id: number;
  endpoint_key: string;
  change_type: 'added' | 'modified' | 'removed' | string;
  tag: string;
  summary: string;
  source_file?: string | null;
  source_line?: number | null;
  created_at: string;
  before_json?: Record<string, unknown> | null;
  after_json?: Record<string, unknown> | null;
  diff_json?: Record<string, unknown> | null;
  scan_run?: ApiMonitorScanRun;
}

export interface ApiMonitorScanRunChanges {
  scan_run: ApiMonitorScanRun;
  changes: ApiMonitorEndpointChange[];
}

