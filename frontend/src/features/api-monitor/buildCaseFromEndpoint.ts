import type { ApiMonitorEndpoint, ApiMonitorParameter } from '../../types/apiMonitor';
import type { ApiTestCaseFormValues } from '../../types/apiTestCase';
import { buildCombinedRequestParamsField } from '../../utils/caseRequestParts';
import { buildDebugRequestBody } from './debugUtils';

function defaultSampleValue(dataType: string): unknown {
  const lower = dataType.toLowerCase();
  if (lower.includes('int') || lower.includes('long') || lower.includes('number')) return 0;
  if (lower.includes('bool')) return false;
  if (lower.includes('array') || lower.includes('list')) return [];
  if (lower.includes('object') || lower.includes('dict')) return {};
  return '';
}

export function buildRequestParamsJson(parameters: ApiMonitorParameter[]): string | undefined {
  const query: Record<string, unknown> = {};
  const path: Record<string, unknown> = {};
  for (const param of parameters) {
    const sample = defaultSampleValue(param.data_type);
    if (param.in === 'query') {
      query[param.name] = sample;
    } else if (param.in === 'path') {
      path[param.name] = sample;
    }
  }
  if (!Object.keys(query).length && !Object.keys(path).length) {
    return undefined;
  }
  return JSON.stringify({ query, path }, null, 2);
}

export function buildCaseDefaultsFromEndpoint(
  endpoint: ApiMonitorEndpoint,
  context: {
    project_id: number;
    environment_id: number;
    service: string;
  },
): ApiTestCaseFormValues {
  const bodyParams = endpoint.parameters.filter((item) => item.in === 'body');
  const summary = endpoint.summary?.trim() || endpoint.path;
  const requestParams = buildRequestParamsJson(endpoint.parameters);
  const requestBody = bodyParams.length ? buildDebugRequestBody(bodyParams) : undefined;
  return {
    project_id: context.project_id,
    environment_id: context.environment_id,
    service: context.service,
    name: `${summary}-冒烟`,
    api_path: endpoint.path,
    method: endpoint.method,
    request_params_combined: buildCombinedRequestParamsField(requestParams, requestBody),
    expected_status: 200,
    expected_response: undefined,
    case_type: 'smoke',
    endpoint_id: endpoint.id,
  };
}

export { parseCaseRequestParams, resolveCaseHeaders } from '../../utils/caseRequestParts';
