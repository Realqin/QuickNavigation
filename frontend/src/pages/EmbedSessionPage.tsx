import { App, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  cancelEmbedSessionClose,
  loadEmbedSessionUrl,
  registerEmbedSessionCleanup,
  scheduleEmbedSessionClose,
} from '../utils/embedSession';
import { showApiError } from '../utils/apiError';

export default function EmbedSessionPage() {
  const { message } = App.useApp();
  const { sessionId = '' } = useParams();
  const [loading, setLoading] = useState(true);
  const [src, setSrc] = useState('');

  useEffect(() => {
    if (!sessionId) {
      setLoading(false);
      return;
    }

    cancelEmbedSessionClose(sessionId);

    let cancelled = false;
    setLoading(true);
    loadEmbedSessionUrl(sessionId)
      .then((url) => {
        if (!cancelled) {
          setSrc(url);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          showApiError(error, '加载控制台会话失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    const unregisterCleanup = registerEmbedSessionCleanup(sessionId);
    return () => {
      cancelled = true;
      unregisterCleanup();
      scheduleEmbedSessionClose(sessionId);
    };
  }, [sessionId, message]);

  if (loading) {
    return (
      <div className="embedded-console-page embedded-console-page--standalone embedded-console-page--loading">
        <Spin size="large" tip="加载控制台..." />
      </div>
    );
  }

  if (!src) {
    return (
      <div className="embedded-console-page embedded-console-page--standalone embedded-console-page--loading">
        <Typography.Text type="secondary">会话无效或已关闭</Typography.Text>
      </div>
    );
  }

  return (
    <div className="embedded-console-page embedded-console-page--standalone">
      <iframe title={`embed-session-${sessionId}`} src={src} className="embedded-console-frame" />
    </div>
  );
}
