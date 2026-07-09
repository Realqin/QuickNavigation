type Params = Record<string, unknown> | undefined;

function buildGetKey(url: string, params?: Params): string {
  if (!params || Object.keys(params).length === 0) {
    return url;
  }
  const normalized = Object.keys(params)
    .filter((key) => params[key] !== undefined && params[key] !== null)
    .sort()
    .map((key) => `${key}=${String(params[key])}`)
    .join('&');
  return normalized ? `${url}?${normalized}` : url;
}

const inflight = new Map<string, Promise<unknown>>();

/** 合并相同 GET 请求的 in-flight Promise，避免页面多处同时触发重复请求。 */
export function coalesceGet<T>(url: string, params: Params, fetcher: () => Promise<T>): Promise<T> {
  const key = buildGetKey(url, params);
  const pending = inflight.get(key);
  if (pending) {
    return pending as Promise<T>;
  }
  const promise = fetcher().finally(() => {
    if (inflight.get(key) === promise) {
      inflight.delete(key);
    }
  });
  inflight.set(key, promise);
  return promise;
}

export function clearGetCoalesce(): void {
  inflight.clear();
}
