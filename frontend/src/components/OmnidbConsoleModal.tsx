import { FullscreenExitOutlined, FullscreenOutlined } from '@ant-design/icons';
import { Button, Modal, Spin, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { openOmnidbConsole } from '../api';
import { showApiError } from '../utils/apiError';
import { resolveOmnidbOpenUrl } from '../utils/omnidb';

interface Props {
  open: boolean;
  connectionId: number | null;
  connectionName?: string;
  onClose: () => void;
}

export default function OmnidbConsoleModal({
  open,
  connectionId,
  connectionName,
  onClose,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [embedUrl, setEmbedUrl] = useState('');
  const [title, setTitle] = useState('数据库控制台');
  const [fullscreen, setFullscreen] = useState(true);

  useEffect(() => {
    if (!open || !connectionId) {
      setEmbedUrl('');
      return;
    }

    let cancelled = false;
    setLoading(true);
    openOmnidbConsole(connectionId)
      .then((data) => {
        if (cancelled) return;
        setEmbedUrl(resolveOmnidbOpenUrl(data.embed_url));
        setTitle(data.connection_name || connectionName || '数据库控制台');
      })
      .catch((error) => {
        if (!cancelled) {
          showApiError(error, '打开数据库控制台失败');
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
  }, [open, connectionId, connectionName]);

  return (
    <Modal
      title={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <span>OmniDB · {title}</span>
          <Button
            type="text"
            size="small"
            icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            onClick={() => setFullscreen((value) => !value)}
          />
        </div>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
      width={fullscreen ? '96vw' : 1080}
      style={fullscreen ? { top: 12, paddingBottom: 0 } : undefined}
      styles={{
        body: {
          height: fullscreen ? 'calc(100vh - 110px)' : 720,
          padding: 0,
          overflow: 'hidden',
        },
      }}
    >
      {loading ? (
        <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
          <Spin tip="正在同步连接并登录 OmniDB..." />
        </div>
      ) : embedUrl ? (
        <iframe
          title={`OmniDB ${title}`}
          src={embedUrl}
          style={{ width: '100%', height: '100%', border: 'none' }}
          allow="clipboard-read; clipboard-write"
        />
      ) : (
        <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
          <Typography.Text type="secondary">无法加载 OmniDB</Typography.Text>
        </div>
      )}
    </Modal>
  );
}
