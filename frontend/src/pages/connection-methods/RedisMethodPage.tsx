import { App, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { fetchRedisinsightMenuUrl } from '../../api';
import { resolveRedisinsightOpenUrl } from '../../utils/redisinsight';
import { showApiError } from '../../utils/apiError';

/** 菜单入口：清理临时连接后进入 RedisInsight */
export default function RedisMethodPage() {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [src, setSrc] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchRedisinsightMenuUrl()
      .then((data) => {
        if (!cancelled) {
          setSrc(resolveRedisinsightOpenUrl(data.url));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          showApiError(error, '加载 Redis 控制台失败');
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
        <Spin size="large" tip="准备 Redis 控制台..." />
      </div>
    );
  }

  if (!src) {
    return (
      <div className="embedded-console-page embedded-console-page--loading">
        <Typography.Text type="secondary">
          无法加载 Redis 控制台，请确认 RedisInsight 已启动（端口 5540）
        </Typography.Text>
      </div>
    );
  }

  return (
    <div className="embedded-console-page">
      <iframe title="redisinsight-menu" src={src} className="embedded-console-frame" />
    </div>
  );
}
