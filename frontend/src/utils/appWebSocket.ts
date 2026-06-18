/** 构建指向本应用后端的 WebSocket 地址 */
export function buildAppWebSocketUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${normalized}`;
}

/**
 * 开发环境直连后端 8000（绕过 Vite WebSocket 代理，更稳定）
 * 生产环境走同源 /ws（Nginx 反代）
 */
export function buildMqttBridgeWebSocketUrl(connectionId: number): string {
  const id = Math.trunc(Number(connectionId));
  if (!Number.isFinite(id) || id <= 0) {
    throw new Error('无效的 MQTT 连接 ID');
  }
  if (import.meta.env.DEV) {
    const host = window.location.hostname;
    return `ws://${host}:8000/ws/mqtt/${id}`;
  }
  return buildAppWebSocketUrl(`/ws/mqtt/${id}`);
}

export function buildMqttManualBridgeWebSocketUrl(): string {
  if (import.meta.env.DEV) {
    const host = window.location.hostname;
    return `ws://${host}:8000/ws/mqtt/manual`;
  }
  return buildAppWebSocketUrl('/ws/mqtt/manual');
}

export function buildLogsWebSocketUrl(): string {
  if (import.meta.env.DEV) {
    const host = window.location.hostname;
    return `ws://${host}:8000/ws/logs`;
  }
  return buildAppWebSocketUrl('/ws/logs');
}
