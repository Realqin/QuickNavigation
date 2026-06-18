import type { ApiMonitorEndpoint, ApiMonitorParameter } from '../../types/apiMonitor';

/** 扫描结果路径已含网关前缀；调试时默认不再额外拼接前缀。 */
export function inferGatewayPathPrefix(_endpoint: ApiMonitorEndpoint): string {
  return '';
}

export function joinRequestPath(pathPrefix: string, path: string): string {
  const prefix = (pathPrefix || '').trim().replace(/\/+$/, '');
  const suffix = (path || '').trim().replace(/^\/+/, '');
  if (!prefix) {
    return `/${suffix}`;
  }
  return `/${prefix}/${suffix}`.replace(/\/+/g, '/');
}

function sampleValueForParam(param: ApiMonitorParameter): unknown {
  if (param.children?.length) {
    const sample: Record<string, unknown> = {};
    for (const child of param.children) {
      sample[child.name] = defaultSampleValue(child.data_type);
    }
    return sample;
  }
  if (param.schema_name && (param.data_type === 'object' || param.in === 'body')) {
    return {};
  }
  return defaultSampleValue(param.data_type);
}

export function buildDebugRequestBody(bodyParams: ApiMonitorParameter[]): string {
  if (!bodyParams.length) {
    return '{}';
  }
  if (bodyParams.length === 1) {
    const param = bodyParams[0];
    return JSON.stringify(sampleValueForParam(param), null, 2);
  }
  const sample: Record<string, unknown> = {};
  for (const param of bodyParams) {
    sample[param.name] = sampleValueForParam(param);
  }
  return JSON.stringify(sample, null, 2);
}

function defaultSampleValue(dataType: string): unknown {
  const lower = dataType.toLowerCase();
  if (lower.includes('int') || lower.includes('long') || lower.includes('number')) return 0;
  if (lower.includes('bool')) return false;
  if (lower.includes('array') || lower.includes('list')) return [];
  if (lower.includes('object') || lower.includes('dict')) return {};
  return '';
}

export function buildDebugUrl(
  baseUrl: string,
  pathPrefix: string,
  path: string,
  pathParams: Record<string, string>,
  queryParams: Record<string, string>,
): string {
  let resolvedPath = joinRequestPath(pathPrefix, path);
  for (const [key, value] of Object.entries(pathParams)) {
    resolvedPath = resolvedPath.replace(`{${key}}`, encodeURIComponent(value));
  }
  const url = new URL(resolvedPath, baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`);
  for (const [key, value] of Object.entries(queryParams)) {
    if (value !== '') {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

export function statusHint(statusCode: number, pathPrefix: string): string | null {
  if (statusCode !== 405) {
    return null;
  }
  if (!pathPrefix.trim()) {
    return '返回 405 通常表示网关路径前缀不正确。若扫描路径未含网关前缀，可在此填写，例如 /api/alarm。';
  }
  return '返回 405 表示当前地址或请求方法不被网关接受，请检查路径前缀、服务地址和请求类型。';
}
