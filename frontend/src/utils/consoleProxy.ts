/** 控制台 embed URL 改写（Kafka 走同源 /proxy；其余控制台直连端口）。 */

const PROXY_PREFIX_BY_PORT: Record<string, string> = {
  '8082': '/proxy/kafka',
};

function resolveDirectConsoleProtocol(defaultPort: number): string {
  if (defaultPort === 8182) {
    const hostname = window.location.hostname;
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      return 'https:';
    }
  }
  return window.location.protocol;
}

/** @deprecated 仅保留给旧 embed URL；新控制台请用各 resolve*OpenUrl 直连端口。 */
export function resolveConsoleProxyUrl(embedUrl: string, proxyPrefix: string): string {
  const prefix = proxyPrefix.endsWith('/') ? proxyPrefix : `${proxyPrefix}/`;
  let path = '/';
  try {
    const parsed = new URL(embedUrl, window.location.origin);
    path = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    path = embedUrl.startsWith('/') ? embedUrl : `/${embedUrl}`;
  }
  if (!path.startsWith('/')) {
    path = `/${path}`;
  }
  const origin = `${window.location.protocol}//${window.location.host}`;
  return `${origin}${prefix.replace(/\/$/, '')}${path}`;
}

export function rewriteEmbedConsoleUrl(embedUrl: string): string {
  return embedUrl.trim();
}

export function resolveServiceConsoleUrl(baseUrl: string | undefined, defaultPort: number): string {
  const prefix = PROXY_PREFIX_BY_PORT[String(defaultPort)];
  if (prefix) {
    return resolveConsoleProxyUrl(baseUrl?.trim() || '/', prefix);
  }
  if (!baseUrl?.trim()) {
    return `${resolveDirectConsoleProtocol(defaultPort)}//${window.location.hostname}:${defaultPort}`;
  }
  const target = new URL(baseUrl);
  target.protocol = resolveDirectConsoleProtocol(defaultPort);
  target.hostname = window.location.hostname;
  target.port = String(defaultPort);
  return target.toString();
}
