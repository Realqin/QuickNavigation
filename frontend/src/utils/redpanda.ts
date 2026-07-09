import { resolveConsoleProxyUrl } from './consoleProxy';

const KAFKA_PROXY_PREFIX = '/proxy/kafka';

/** Kafka UI 走 8080 同源代理（客户端常无法直连 8082）。 */
export function resolveRedpandaOpenUrl(embedUrl: string): string {
  const url = resolveConsoleProxyUrl(embedUrl, KAFKA_PROXY_PREFIX);
  // 必须带尾部 /，否则 nginx 无法匹配 /proxy/kafka/ 会落到 SPA 首页
  return url.endsWith('/') ? url : `${url}/`;
}

export async function openRedpandaInNewTab(
  openConsole: (
    connectionId: number,
    publicHost?: string,
  ) => Promise<{ embed_url: string; session_id?: string | null }>,
  connectionId: number,
): Promise<void> {
  const data = await openConsole(connectionId, window.location.hostname);
  const url = resolveRedpandaOpenUrl(data.embed_url);
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) {
    throw new Error('browser blocked popup');
  }
}
