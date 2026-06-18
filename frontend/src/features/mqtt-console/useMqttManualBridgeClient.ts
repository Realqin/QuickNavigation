import { useCallback, useRef, useState } from 'react';
import type { MqttConnectionForm } from './types';
import { buildAppWebSocketUrl, buildMqttManualBridgeWebSocketUrl } from '../../utils/appWebSocket';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

function buildConnectUrls(): string[] {
  const primary = buildMqttManualBridgeWebSocketUrl();
  const urls = [primary];
  if (import.meta.env.DEV) {
    const viaProxy = buildAppWebSocketUrl('/ws/mqtt/manual');
    if (viaProxy !== primary) {
      urls.push(viaProxy);
    }
  }
  return urls;
}

export function useMqttManualBridgeClient() {
  const wsRef = useRef<WebSocket | null>(null);
  const connectingRef = useRef(false);
  const connectedRef = useRef(false);
  const messageHandlerRef = useRef<((topic: string, payload: string) => void) | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [activeTopics, setActiveTopics] = useState<string[]>([]);
  const [bridgeTarget, setBridgeTarget] = useState<string | null>(null);
  const [bridgeChannel, setBridgeChannel] = useState<string | null>(null);

  const disconnect = useCallback(() => {
    connectingRef.current = false;
    connectedRef.current = false;
    const ws = wsRef.current;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      wsRef.current = null;
    }
    setActiveTopics([]);
    setBridgeTarget(null);
    setBridgeChannel(null);
    setStatus('disconnected');
    setError(null);
  }, []);

  const connectWithUrl = useCallback((url: string, form: MqttConnectionForm) => {
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      let brokerTimer: number | undefined;
      let openTimer: number | undefined;

      const clearTimers = () => {
        if (openTimer) {
          window.clearTimeout(openTimer);
          openTimer = undefined;
        }
        if (brokerTimer) {
          window.clearTimeout(brokerTimer);
          brokerTimer = undefined;
        }
      };

      const finish = (action: 'resolve' | 'reject', value?: Error) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimers();
        if (action === 'resolve') {
          resolve();
        } else {
          reject(value ?? new Error('连接失败'));
        }
      };

      const markWsReady = () => {
        if (openTimer) {
          window.clearTimeout(openTimer);
          openTimer = undefined;
        }
        if (!brokerTimer) {
          brokerTimer = window.setTimeout(
            () =>
              finish(
                'reject',
                new Error(
                  'Broker 连接超时：WebSocket 已连通，但后端在 20 秒内未能连上 MQTT Broker',
                ),
              ),
            20000,
          );
        }
      };

      openTimer = window.setTimeout(
        () =>
          finish(
            'reject',
            new Error(`无法连接后端 WebSocket：${url}（请确认后端已在 8000 端口启动）`),
          ),
        12000,
      );

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        markWsReady();
        ws.send(
          JSON.stringify({
            type: 'connect',
            host: form.host.trim(),
            port: form.port || 1883,
            username: form.username.trim(),
            password: form.password,
          }),
        );
      };

      ws.onmessage = (event) => {
        markWsReady();
        try {
          const data = JSON.parse(event.data as string) as {
            type: string;
            status?: string;
            message?: string;
            topic?: string;
            payload?: string;
            topics?: string[];
            target?: string;
          };

          if (data.type === 'status') {
            if (data.status === 'connecting') {
              if (data.target) {
                setBridgeTarget(data.target);
              }
              return;
            }
            if (data.status === 'connected') {
              connectedRef.current = true;
              setStatus('connected');
              setActiveTopics(data.topics ?? []);
              if (data.target) {
                setBridgeTarget(data.target);
              }
              finish('resolve');
            } else if (data.status === 'error') {
              finish('reject', new Error(data.message || '连接失败'));
            }
            return;
          }

          if (data.type === 'message' && data.topic) {
            const handler = messageHandlerRef.current;
            if (handler) {
              handler(data.topic, data.payload ?? '');
            }
            return;
          }

          if (data.type === 'subscribed' && data.topic) {
            setActiveTopics((prev) =>
              prev.includes(data.topic!) ? prev : [...prev, data.topic!],
            );
          }

          if (data.type === 'unsubscribed' && data.topic) {
            setActiveTopics((prev) => prev.filter((item) => item !== data.topic));
          }
        } catch {
          // ignore malformed payloads
        }
      };

      ws.onerror = () => {
        if (!settled) {
          finish('reject', new Error('WebSocket 连接失败'));
        }
      };

      ws.onclose = () => {
        if (!settled) {
          finish('reject', new Error('连接已关闭'));
        } else if (connectedRef.current) {
          connectedRef.current = false;
          setStatus('disconnected');
        }
      };
    });
  }, []);

  const connect = useCallback(
    async (form: MqttConnectionForm) => {
      if (connectingRef.current || connectedRef.current) {
        return;
      }
      if (!form.host.trim()) {
        throw new Error('请输入主机');
      }

      disconnect();
      connectingRef.current = true;
      setStatus('connecting');
      setError(null);

      const urls = buildConnectUrls();
      setBridgeChannel(urls[0]);
      setBridgeTarget(`mqtt://${form.host.trim()}:${form.port || 1883}`);

      try {
        let lastError: Error | null = null;
        for (const url of urls) {
          setBridgeChannel(url);
          try {
            await connectWithUrl(url, form);
            lastError = null;
            break;
          } catch (err) {
            lastError = err instanceof Error ? err : new Error('连接失败');
            const ws = wsRef.current;
            if (ws) {
              ws.onopen = null;
              ws.onmessage = null;
              ws.onerror = null;
              ws.onclose = null;
              if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                ws.close();
              }
              wsRef.current = null;
            }
          }
        }
        if (lastError) {
          throw lastError;
        }
      } catch (err) {
        connectedRef.current = false;
        setActiveTopics([]);
        setBridgeTarget(null);
        setBridgeChannel(null);
        setStatus('error');
        const messageText = err instanceof Error ? err.message : '连接失败';
        setError(messageText);
        throw err;
      } finally {
        connectingRef.current = false;
      }
    },
    [connectWithUrl, disconnect],
  );

  const sendCommand = useCallback((payload: Record<string, string>) => {
    const ws = wsRef.current;
    if (!connectedRef.current || !ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error('未连接，请先点击连接');
    }
    ws.send(JSON.stringify(payload));
  }, []);

  const subscribe = useCallback(
    async (topic: string) => {
      const normalized = topic.trim();
      if (!normalized || activeTopics.includes(normalized)) {
        return;
      }
      sendCommand({ type: 'subscribe', topic: normalized });
    },
    [activeTopics, sendCommand],
  );

  const unsubscribe = useCallback(
    async (topic: string) => {
      const normalized = topic.trim();
      if (!normalized) {
        return;
      }
      sendCommand({ type: 'unsubscribe', topic: normalized });
    },
    [sendCommand],
  );

  const publish = useCallback(
    async (topic: string, payload: string) => {
      const normalizedTopic = topic.trim();
      if (!normalizedTopic) {
        throw new Error('Topic 为空');
      }
      sendCommand({ type: 'publish', topic: normalizedTopic, payload });
    },
    [sendCommand],
  );

  const bindMessageHandler = useCallback((handler: (topic: string, payload: string) => void) => {
    messageHandlerRef.current = handler;
    return () => {
      if (messageHandlerRef.current === handler) {
        messageHandlerRef.current = null;
      }
    };
  }, []);

  return {
    status,
    error,
    activeTopics,
    bridgeTarget,
    bridgeChannel,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    publish,
    bindMessageHandler,
  };
}
