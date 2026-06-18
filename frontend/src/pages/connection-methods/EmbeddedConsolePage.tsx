import { App, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { fetchPublicConfig } from '../../api';
import type { PublicConfig } from '../../types';
import { resolveServiceBaseUrl } from '../../utils/serviceUrl';

type ConsoleConfigKey = keyof Pick<
  PublicConfig,
  'omnidb_login_url' | 'sshwifty_base_url' | 'redpanda_base_url' | 'redisinsight_base_url'
>;

interface Props {
  configKey: ConsoleConfigKey;
  defaultPort: number;
  emptyHint: string;
  /** 菜单入口：仅加载控制台首页，不绑定连接、不自动连接 */
}

export default function EmbeddedConsolePage({ configKey, defaultPort, emptyHint }: Props) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [src, setSrc] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPublicConfig()
      .then((config) => {
        if (cancelled) return;
        let raw = config[configKey];
        if (!raw?.trim() && configKey === 'omnidb_login_url' && config.omnidb_base_url?.trim()) {
          raw = `${config.omnidb_base_url.replace(/\/$/, '')}/omnidb_login/`;
        }
        const resolved = resolveServiceBaseUrl(raw, defaultPort);
        setSrc(resolved);
      })
      .catch(() => {
        if (!cancelled) {
          message.error('加载控制台地址失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [configKey, defaultPort, message]);

  if (loading) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Spin size="large" tip="加载控制台..." />
      </div>
    );
  }

  if (!src) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Typography.Text type="secondary">{emptyHint}</Typography.Text>
      </div>
    );
  }

  return (
    <div className="embedded-console-page">
      <iframe title={configKey} src={src} className="embedded-console-frame" />
    </div>
  );
}
