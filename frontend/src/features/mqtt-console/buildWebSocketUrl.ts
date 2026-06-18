export interface MqttWebSocketEndpoint {
  host: string;
  port: number;
  wsPath: string;
  protocol: 'ws' | 'wss';
}

/** 浏览器 WebSocket 协议（ws/wss），与挂载路径 /mqtt 无关 */
export function resolveWebSocketProtocol(): 'ws' | 'wss' {
  return window.location.protocol === 'https:' ? 'wss' : 'ws';
}

/** 从主机输入解析 endpoint（支持 mqtt://、ws://host:port/mqtt） */
export function parseMqttHostInput(
  rawHost: string,
  defaultPort: number,
  defaultPath: string,
): MqttWebSocketEndpoint {
  const normalizedDefaultPath = defaultPath.startsWith('/') ? defaultPath : `/${defaultPath}`;
  let input = rawHost.trim();
  if (!input) {
    return {
      host: '',
      port: defaultPort,
      wsPath: normalizedDefaultPath,
      protocol: resolveWebSocketProtocol(),
    };
  }

  if (/^(mqtt|wss?):\/\//i.test(input)) {
    try {
      const url = new URL(input.replace(/^mqtt:\/\//i, 'ws://'));
      const wsPath =
        url.pathname && url.pathname !== '/' ? url.pathname : normalizedDefaultPath;
      const protocol: 'ws' | 'wss' = url.protocol === 'wss:' ? 'wss' : 'ws';
      return {
        host: url.hostname,
        port: url.port ? Number(url.port) : defaultPort,
        wsPath: wsPath.startsWith('/') ? wsPath : `/${wsPath}`,
        protocol,
      };
    } catch {
      input = input.replace(/^(mqtt|wss?):\/\//i, '');
    }
  }

  input = input.replace(/^https?:\/\//i, '');

  let hostPart = input;
  let wsPath = normalizedDefaultPath;

  const slashIndex = input.indexOf('/');
  if (slashIndex >= 0) {
    hostPart = input.slice(0, slashIndex);
    const pathPart = input.slice(slashIndex);
    wsPath = pathPart.startsWith('/') ? pathPart : `/${pathPart}`;
  }

  let host = hostPart;
  let port = defaultPort;
  const colonIndex = hostPart.lastIndexOf(':');
  if (colonIndex > 0 && !hostPart.includes(']')) {
    const portText = hostPart.slice(colonIndex + 1);
    if (/^\d+$/.test(portText)) {
      host = hostPart.slice(0, colonIndex);
      port = Number(portText);
    }
  }

  return {
    host,
    port,
    wsPath: wsPath.startsWith('/') ? wsPath : `/${wsPath}`,
    protocol: resolveWebSocketProtocol(),
  };
}

/** 完整 WebSocket 地址预览：ws://host:port/mqtt（路径为 /mqtt，不是 /ws） */
export function buildMqttWebSocketUrl(host: string, port: number, wsPath: string): string {
  const endpoint = parseMqttHostInput(host, port, wsPath.trim() || '/mqtt');
  if (!endpoint.host) {
    return `${endpoint.protocol}://:${endpoint.port}${endpoint.wsPath}`;
  }
  return `${endpoint.protocol}://${endpoint.host}:${endpoint.port}${endpoint.wsPath}`;
}

/** mqtt.js 连接用：仅 host:port，路径通过 path 选项传入 */
export function buildMqttConnectTarget(host: string, port: number, wsPath: string): MqttWebSocketEndpoint {
  return parseMqttHostInput(host, port, wsPath.trim() || '/mqtt');
}
