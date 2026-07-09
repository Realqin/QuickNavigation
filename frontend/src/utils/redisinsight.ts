const DEFAULT_REDISINSIGHT_PORT = 5540;

/** RedisInsight 直连 5540（子路径代理下易跳回 8080 首页）。 */
export function resolveRedisinsightOpenUrl(
  embedUrl: string,
  port = DEFAULT_REDISINSIGHT_PORT,
): string {
  const target = new URL(embedUrl, window.location.origin);
  target.protocol = window.location.protocol;
  target.hostname = window.location.hostname;
  target.port = String(port);
  return target.toString();
}

export async function openRedisinsightInNewTab(
  openConsole: (
    connectionId: number,
    publicHost?: string,
  ) => Promise<{ embed_url: string; session_id?: string | null }>,
  connectionId: number,
): Promise<void> {
  const data = await openConsole(connectionId, window.location.hostname);
  const url = resolveRedisinsightOpenUrl(data.embed_url);
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) {
    throw new Error('browser blocked popup');
  }
}
