import { App, Spin, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { MqttConsoleConfig } from '../../types';
import { fetchMqttConfig } from './api';
import {
  cancelEmbedSessionClose,
  registerEmbedSessionCleanup,
  scheduleEmbedSessionClose,
} from '../../utils/embedSession';
import { showApiError } from '../../utils/apiError';
import MqttConsole from './MqttConsole';

export default function MqttConsolePage() {
  const { message } = App.useApp();
  const [searchParams] = useSearchParams();
  const connectionId = Number(searchParams.get('connectionId') || '');
  const sessionId = searchParams.get('sessionId') || '';
  const [loading, setLoading] = useState(Boolean(connectionId));
  const [config, setConfig] = useState<MqttConsoleConfig | null>(null);

  useEffect(() => {
    if (!connectionId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchMqttConfig(connectionId)
      .then(setConfig)
      .catch((error) => showApiError(error, '加载 MQTT 连接配置失败'))
      .finally(() => setLoading(false));
  }, [connectionId]);

  useEffect(() => {
    if (!sessionId) {
      return undefined;
    }
    cancelEmbedSessionClose(sessionId);
    const unregisterCleanup = registerEmbedSessionCleanup(sessionId);
    return () => {
      unregisterCleanup();
      scheduleEmbedSessionClose(sessionId);
    };
  }, [sessionId]);

  const initialConnection = useMemo(
    () =>
      config
        ? {
            host: config.host,
            port: config.port,
            wsPath: config.ws_path,
            username: config.username,
            password: config.password,
          }
        : undefined,
    [config],
  );

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" tip="加载连接配置..." />
      </div>
    );
  }

  if (connectionId && !config) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography.Text type="secondary">无法加载 MQTT 连接，请从导航重新打开</Typography.Text>
      </div>
    );
  }

  return (
    <MqttConsole
      connectionName={config?.connection_name}
      presetSubscriptions={config?.subscriptions ?? []}
      initialConnection={initialConnection}
      bridgeConnectionId={connectionId > 0 ? connectionId : undefined}
      manualBridge={!(connectionId > 0)}
    />
  );
}
