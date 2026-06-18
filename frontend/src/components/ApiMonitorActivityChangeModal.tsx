import { Button, List, Modal, Space, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { fetchApiMonitorScanRunChanges } from '../api';
import ApiMonitorChangeCompareView from '../features/api-monitor/ApiMonitorChangeCompareView';
import type { ActivityLog } from '../types';
import type { ApiMonitorEndpointChange } from '../types/apiMonitor';
import { formatBeijingTime } from '../utils/dateTime';
import { buildApiMonitorServiceId, isApiMonitorChangeLog } from '../utils/apiMonitorChangeLog';

interface Props {
  log: ActivityLog | null;
  open: boolean;
  onClose: () => void;
}

const CHANGE_TYPE_COLORS: Record<string, string> = {
  added: 'green',
  modified: 'blue',
  removed: 'red',
};

export default function ApiMonitorActivityChangeModal({ log, open, onClose }: Props) {
  const [changes, setChanges] = useState<ApiMonitorEndpointChange[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    if (!open || !log || !isApiMonitorChangeLog(log)) {
      setChanges([]);
      setExpandedId(null);
      return;
    }
    const serviceId = buildApiMonitorServiceId(log);
    const scanRunId = log.payload?.scan_run_id;
    if (!serviceId || typeof scanRunId !== 'number') {
      setChanges([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchApiMonitorScanRunChanges(serviceId, scanRunId)
      .then((data) => {
        if (!cancelled) {
          setChanges(data.changes);
          setExpandedId(data.changes[0]?.id ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) setChanges([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [log, open]);

  return (
    <Modal
      title={log ? `接口变更详情 · ${changes.length} 项` : '接口变更详情'}
      open={open}
      onCancel={onClose}
      footer={null}
      width={1080}
      destroyOnHidden
      className="api-monitor-change-compare-modal"
    >
      {log?.summary ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 13 }}>
          {log.summary}
        </Typography.Paragraph>
      ) : null}

      <List
        loading={loading}
        size="small"
        dataSource={changes}
        locale={{ emptyText: '暂无变更明细' }}
        renderItem={(item) => {
          const expanded = expandedId === item.id;
          return (
            <List.Item style={{ display: 'block', paddingInline: 0 }}>
              <Space size={8} wrap style={{ marginBottom: expanded ? 12 : 0 }}>
                <Tag color={CHANGE_TYPE_COLORS[item.change_type] || 'default'}>{item.change_type}</Tag>
                <Typography.Text code>{item.endpoint_key}</Typography.Text>
                <Typography.Text type="secondary">{item.summary}</Typography.Text>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0 }}
                  onClick={() => setExpandedId(expanded ? null : item.id)}
                >
                  {expanded ? '收起对比' : '查看对比'}
                </Button>
              </Space>
              {expanded ? <ApiMonitorChangeCompareView change={item} /> : null}
            </List.Item>
          );
        }}
      />

      {log?.occurred_at ? (
        <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
          扫描时间：{formatBeijingTime(log.occurred_at) || log.occurred_at}
        </Typography.Text>
      ) : null}
    </Modal>
  );
}
