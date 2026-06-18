import { App, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { fetchOmnidbMenuUrl } from '../../api';
import { resolveServiceBaseUrl } from '../../utils/serviceUrl';

const DEFAULT_OMNIDB_PORT = 8081;

/** 菜单入口：清空工作区后进入 OmniDB，由用户自行选择或添加连接 */
export default function OmnidbMethodPage() {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [src, setSrc] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchOmnidbMenuUrl()
      .then((data) => {
        if (!cancelled) {
          setSrc(resolveServiceBaseUrl(data.url, DEFAULT_OMNIDB_PORT));
        }
      })
      .catch(() => {
        if (!cancelled) {
          message.error('加载数据库控制台失败');
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

  if (loading) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Spin size="large" tip="准备数据库控制台..." />
      </div>
    );
  }

  if (!src) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Typography.Text type="secondary">
          无法加载数据库控制台，请确认 OmniDB 已启动（端口 8081）
        </Typography.Text>
      </div>
    );
  }

  return (
    <div className="embedded-console-page">
      <iframe title="omnidb-menu" src={src} className="embedded-console-frame" />
    </div>
  );
}
