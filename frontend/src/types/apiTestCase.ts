export type ApiTestCaseStatus = 'active' | 'deleted';
export type ApiTestCaseType = 'smoke' | 'boundary' | 'regression' | 'custom';
export type ResponseAssertMode = 'text' | 'jsonpath';

export interface ApiTestCase {
  id: number;
  project_id: number;
  environment_id: number;
  project_display: string;
  environment_display: string;
  service: string;
  name: string;
  api_path: string;
  method: string;
  request_headers?: string | null;
  request_params?: string | null;
  request_body?: string | null;
  expected_status: number;
  expected_response?: string | null;
  response_assert_mode?: ResponseAssertMode | string;
  response_assert_rules?: string | null;
  case_type: ApiTestCaseType | string;
  status: ApiTestCaseStatus | string;
  endpoint_id?: string | null;
  last_exec_pass?: boolean | null;
  last_exec_status_code?: number | null;
  last_exec_response?: string | null;
  last_exec_detail?: string | null;
  last_exec_at?: string | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

export interface ApiTestCaseList {
  items: ApiTestCase[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiTestCaseFormValues {
  project_id: number;
  environment_id: number;
  service: string;
  name: string;
  api_path: string;
  method: string;
  request_headers?: string;
  request_params?: string;
  request_body?: string;
  /** 表单内合并展示 query/path/body，提交时拆分 */
  request_params_combined?: string;
  expected_status: number;
  expected_response?: string;
  response_assert_mode?: ResponseAssertMode | string;
  response_assert_rules?: string;
  case_type: ApiTestCaseType | string;
  endpoint_id?: string;
}

export const API_TEST_CASE_TYPE_LABELS: Record<string, string> = {
  smoke: '冒烟',
  boundary: '边界',
  regression: '回归',
  custom: '自定义',
};

export const API_TEST_CASE_TYPE_OPTIONS = Object.entries(API_TEST_CASE_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

export const HTTP_METHOD_OPTIONS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => ({
  value: method,
  label: method,
}));

export const API_TEST_CASE_STATUS_OPTIONS = [
  { label: '正常', value: 'active' },
  { label: '已删除', value: 'deleted' },
  { label: '全部', value: 'all' },
];
