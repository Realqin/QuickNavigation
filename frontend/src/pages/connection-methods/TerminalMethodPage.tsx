import { App, Button, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { fetchPublicConfig } from '../../api';
import { showApiError } from '../../utils/apiError';
import { resolveSshwiftyOpenUrl } from '../../utils/sshwifty';

/** 连接方式 → 终端：须在顶级 HTTPS 窗口打开，iframe 内 crypto.subtle 不可用。 */
export default function TerminalMethodPage() {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [terminalUrl, setTerminalUrl] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPublicConfig()
      .then((config) => {
        if (cancelled) return;
        const raw = config.sshwifty_base_url?.trim();
        if (!raw) {
          setTerminalUrl('');
          return;
        }
        setTerminalUrl(resolveSshwiftyOpenUrl(raw));
      })
      .catch((error) => {
        if (!cancelled) {
          showApiError(error, '加载终端地址失败');
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
  }, [message]);

  const openTerminal = () => {
    if (!terminalUrl) {
      message.warning('终端服务未配置');
      return;
    }
    const opened = window.open(terminalUrl, '_blank', 'noopener,noreferrer');
    if (!opened) {
      message.warning('浏览器拦截了新标签页，请允许弹窗后重试');
    }
  };

  if (loading) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Spin size="large" tip="加载终端控制台..." />
      </div>
    );
  }

  if (!terminalUrl) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Typography.Text type="secondary">
          无法加载终端控制台，请确认 Sshwifty 已启动（端口 8182）
        </Typography.Text>
      </div>
    );
  }

  return (
    <div className="embedded-console-page embedded-console-page--loading">
      <div style={{ textAlign: 'center', maxWidth: 480, padding: 24 }}>
        <Typography.Title level={4} style={{ marginBottom: 12 }}>
          Linux 终端（Sshwifty）
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          出于浏览器安全策略，SSH 终端须在独立窗口通过 HTTPS 打开，不能内嵌在本页。
          首次访问需接受自签证书。
        </Typography.Paragraph>
        <Button type="primary" size="large" onClick={openTerminal}>
          在新标签页打开终端
        </Button>
      </div>
    </div>
  );
}
