import mqtt, { type MqttClient } from 'mqtt';
import { useCallback, useRef, useState } from 'react';
import { buildMqttConnectTarget, buildMqttWebSocketUrl } from './buildWebSocketUrl';
import type { MqttConnectionForm } from './types';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

function subscribeTopic(client: MqttClient, topic: string): Promise<void> {
  return new Promise((resolve, reject) => {
    client.subscribe(topic, (err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

function unsubscribeTopic(client: MqttClient, topic: string): Promise<void> {
  return new Promise((resolve, reject) => {
    client.unsubscribe(topic, (err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

function publishMessage(client: MqttClient, topic: string, payload: string): Promise<void> {
  return new Promise((resolve, reject) => {
    client.publish(topic, payload, (err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

function destroyClient(client: MqttClient) {
  client.options.reconnectPeriod = 0;
  client.removeAllListeners();
  client.end(true);
}

export function useMqttClient() {
  const clientRef = useRef<MqttClient | null>(null);
  const connectingRef = useRef(false);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [activeTopics, setActiveTopics] = useState<string[]>([]);

  const disconnect = useCallback(() => {
    connectingRef.current = false;
    const client = clientRef.current;
    if (client) {
      destroyClient(client);
      clientRef.current = null;
    }
    setActiveTopics([]);
    setStatus('disconnected');
    setError(null);
  }, []);

  const connect = useCallback(
    async (form: MqttConnectionForm, presetTopics: string[] = []) => {
      if (connectingRef.current || clientRef.current?.connected) {
        return;
      }

      disconnect();
      connectingRef.current = true;
      setStatus('connecting');
      setError(null);

      const wsPath = form.wsPath.trim() || '/mqtt';
      const endpoint = buildMqttConnectTarget(form.host.trim(), form.port, wsPath);
      if (!endpoint.host) {
        throw new Error('请输入主机');
      }
      const brokerUrl = buildMqttWebSocketUrl(form.host.trim(), form.port, wsPath);
      const wsBaseUrl = `${endpoint.protocol}://${endpoint.host}:${endpoint.port}`;
      const clientId = form.clientId.trim() || `quicknav_${Date.now()}`;

      let client: MqttClient | null = null;

      try {
        // path 显式设为 /mqtt（Broker 挂载路径），与 ws/wss 协议前缀无关
        client = mqtt.connect(wsBaseUrl, {
          path: endpoint.wsPath,
          clientId,
          username: form.username.trim() || undefined,
          password: form.password || undefined,
          reconnectPeriod: 0,
          reconnect: false,
          connectTimeout: 12000,
        });

        clientRef.current = client;

        await new Promise<void>((resolve, reject) => {
          let settled = false;
          const finish = (action: 'resolve' | 'reject', value?: Error) => {
            if (settled) {
              return;
            }
            settled = true;
            window.clearTimeout(timer);
            if (action === 'resolve') {
              resolve();
            } else {
              reject(value ?? new Error('连接失败'));
            }
          };

          const timer = window.setTimeout(
            () =>
              finish(
                'reject',
                new Error(
                  `连接超时：${brokerUrl}。请确认 WS 端口与路径正确（非 TCP 1883），且浏览器可访问该地址`,
                ),
              ),
            15000,
          );

          client!.once('connect', () => finish('resolve'));
          client!.once('error', (err) => finish('reject', err));
          client!.once('close', () => {
            if (!settled) {
              finish('reject', new Error('连接已关闭'));
            }
          });
        });

        setStatus('connected');
        const subscribed: string[] = [];
        for (const topic of presetTopics) {
          const normalized = topic.trim();
          if (!normalized) continue;
          await subscribeTopic(client, normalized);
          subscribed.push(normalized);
        }
        setActiveTopics(subscribed);
      } catch (err) {
        if (client) {
          destroyClient(client);
          if (clientRef.current === client) {
            clientRef.current = null;
          }
        }
        setActiveTopics([]);
        setStatus('error');
        const messageText = err instanceof Error ? err.message : '连接失败';
        setError(messageText.includes(brokerUrl) ? messageText : `${messageText}（${brokerUrl}）`);
        throw err;
      } finally {
        connectingRef.current = false;
      }
    },
    [disconnect],
  );

  const subscribe = useCallback(
    async (topic: string) => {
      const client = clientRef.current;
      const normalized = topic.trim();
      if (!client || !normalized) {
        return;
      }
      if (activeTopics.includes(normalized)) {
        return;
      }
      await subscribeTopic(client, normalized);
      setActiveTopics((prev) => [...prev, normalized]);
    },
    [activeTopics],
  );

  const unsubscribe = useCallback(async (topic: string) => {
    const client = clientRef.current;
    const normalized = topic.trim();
    if (!client || !normalized) {
      return;
    }
    await unsubscribeTopic(client, normalized);
    setActiveTopics((prev) => prev.filter((item) => item !== normalized));
  }, []);

  const publish = useCallback(async (topic: string, payload: string) => {
    const client = clientRef.current;
    const normalizedTopic = topic.trim();
    if (!client || !normalizedTopic) {
      throw new Error('未连接或 Topic 为空');
    }
    await publishMessage(client, normalizedTopic, payload);
  }, []);

  const bindMessageHandler = useCallback((handler: (topic: string, payload: Buffer) => void) => {
    const client = clientRef.current;
    if (!client) {
      return () => undefined;
    }
    const onMessage = (topic: string, payload: Buffer) => handler(topic, payload);
    client.on('message', onMessage);
    return () => client.off('message', onMessage);
  }, []);

  return {
    status,
    error,
    activeTopics,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    publish,
    bindMessageHandler,
  };
}
