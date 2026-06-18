function tryParseJson(raw?: string | null): Record<string, unknown> | null {
  if (!raw?.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function toPrettyJson(value: unknown): string | undefined {
  if (value == null) {
    return undefined;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const parsed = tryParseJson(trimmed);
    return parsed ? JSON.stringify(parsed, null, 2) : trimmed;
  }
  return JSON.stringify(value, null, 2);
}

/** 从独立字段或 legacy request_params.headers 读取请求头 */
export function resolveCaseHeaders(
  requestHeaders?: string | null,
  requestParams?: string | null,
): Record<string, string> {
  const direct = tryParseJson(requestHeaders);
  if (direct) {
    return Object.fromEntries(
      Object.entries(direct).map(([key, value]) => [key, String(value ?? '')]),
    );
  }

  const legacy = tryParseJson(requestParams);
  const headers = legacy?.headers;
  if (headers && typeof headers === 'object' && !Array.isArray(headers)) {
    return Object.fromEntries(
      Object.entries(headers as Record<string, unknown>).map(([key, value]) => [key, String(value ?? '')]),
    );
  }
  return {};
}

export function formatCaseHeadersDisplay(
  requestHeaders?: string | null,
  requestParams?: string | null,
): string | undefined {
  const headers = resolveCaseHeaders(requestHeaders, requestParams);
  if (!Object.keys(headers).length) {
    return undefined;
  }
  return JSON.stringify(headers, null, 2);
}

export function parseCaseRequestParams(raw?: string | null): {
  query: Record<string, string>;
  path: Record<string, string>;
} {
  const parsed = tryParseJson(raw);
  if (!parsed) {
    return { query: {}, path: {} };
  }

  const toStringMap = (value: unknown) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, String(item ?? '')]),
    );
  };

  if (parsed.query || parsed.path) {
    return {
      query: toStringMap(parsed.query),
      path: toStringMap(parsed.path),
    };
  }

  const { headers: _headers, ...rest } = parsed;
  return {
    query: toStringMap(rest),
    path: {},
  };
}

/** 表格「请求参数」列：query/path/body 合并展示，不含 headers */
export function formatCaseRequestParamsDisplay(
  requestParams?: string | null,
  requestBody?: string | null,
): string | undefined {
  const { query, path } = parseCaseRequestParams(requestParams);
  const payload: Record<string, unknown> = {};

  if (Object.keys(query).length) {
    payload.query = query;
  }
  if (Object.keys(path).length) {
    payload.path = path;
  }

  const bodyParsed = tryParseJson(requestBody);
  if (bodyParsed) {
    payload.body = bodyParsed;
  } else if (requestBody?.trim()) {
    payload.body = requestBody.trim();
  }

  if (!Object.keys(payload).length) {
    return undefined;
  }
  return JSON.stringify(payload, null, 2);
}

/** 表单编辑：合并为单个「请求参数」JSON */
export function buildCombinedRequestParamsField(
  requestParams?: string | null,
  requestBody?: string | null,
): string | undefined {
  return formatCaseRequestParamsDisplay(requestParams, requestBody);
}

/** 表单保存：拆回 request_params / request_body */
export function splitCombinedRequestParams(raw?: string | null): {
  request_params?: string;
  request_body?: string;
} {
  const parsed = tryParseJson(raw);
  if (!parsed) {
    const trimmed = raw?.trim();
    return trimmed ? { request_params: trimmed } : {};
  }

  const { query, path, body, headers: _headers, ...rest } = parsed;
  const paramsPayload: Record<string, unknown> = {};

  if (query && typeof query === 'object') {
    paramsPayload.query = query;
  }
  if (path && typeof path === 'object') {
    paramsPayload.path = path;
  }

  const restKeys = Object.keys(rest);
  if (restKeys.length && !paramsPayload.query && !paramsPayload.path) {
    paramsPayload.query = rest;
  }

  const result: { request_params?: string; request_body?: string } = {};
  if (Object.keys(paramsPayload).length) {
    result.request_params = JSON.stringify(paramsPayload, null, 2);
  }
  if (body !== undefined) {
    result.request_body = toPrettyJson(body);
  }
  return result;
}

export function formatJsonField(value?: string | null): string | undefined {
  if (value == null) {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  return toPrettyJson(trimmed) ?? trimmed;
}
