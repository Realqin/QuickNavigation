const DEFAULT_SSHWIFTY_PORT = 8182;

function resolveSshwiftyProtocol(): string {
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return window.location.protocol;
  }
  // 局域网 IP 走 HTTP 时浏览器禁用 crypto.subtle，Sshwifty 须 HTTPS
  return 'https:';
}

/** SSH 终端直连 8182（须 HTTPS 安全上下文，否则 importKey 报错）。 */
export function resolveSshwiftyOpenUrl(embedUrl: string, port = DEFAULT_SSHWIFTY_PORT): string {
  const target = new URL(embedUrl, window.location.origin);
  target.protocol = resolveSshwiftyProtocol();
  target.hostname = window.location.hostname;
  target.port = String(port);
  return target.toString();
}

export async function openSshwiftyInNewTab(
  openConsole: (
    connectionId: number,
    publicHost?: string,
  ) => Promise<{ embed_url: string; session_id?: string | null }>,
  connectionId: number,
): Promise<void> {
  const data = await openConsole(connectionId, window.location.hostname);
  const url = resolveSshwiftyOpenUrl(data.embed_url);
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) {
    throw new Error('browser blocked popup');
  }
}
