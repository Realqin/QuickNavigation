import { Button, Empty, Spin, Table, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import ApiMonitorChangeCompareModal from '../../components/ApiMonitorChangeCompareModal';
import { fetchApiMonitorEndpointChanges } from '../../api';
import type { ApiMonitorEndpoint, ApiMonitorEndpointChange } from '../../types/apiMonitor';
import { formatBeijingTime } from '../../utils/dateTime';

interface ApiMonitorChangePanelProps {
  serviceId: string;
  endpoint: ApiMonitorEndpoint;
}

const CHANGE_TYPE_COLORS: Record<string, string> = {
  added: 'green',
  modified: 'blue',
  removed: 'red',
};

const CHANGE_TYPE_LABELS: Record<string, string> = {
  added: '新增',
  modified: '修改',
  removed: '删除',
};

function shortSha(sha?: string | null): string {
  if (!sha) return '-';
  return sha.slice(0, 8);
}

function CompareAction({ onClick }: { onClick: () => void }) {
  return (
    <Button type="link" size="small" style={{ padding: 0 }} onClick={onClick}>
      对比
    </Button>
  );
}

export default function ApiMonitorChangePanel({ serviceId, endpoint }: ApiMonitorChangePanelProps) {
  const [endpointChanges, setEndpointChanges] = useState<ApiMonitorEndpointChange[]>([]);
  const [loading, setLoading] = useState(true);
  const [compareChange, setCompareChange] = useState<ApiMonitorEndpointChange | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);

  const openCompare = (change: ApiMonitorEndpointChange) => {
    setCompareChange(change);
    setCompareOpen(true);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchApiMonitorEndpointChanges(serviceId, endpoint.id, 30)
      .then((changes) => {
        if (!cancelled) setEndpointChanges(changes);
      })
      .catch(() => {
        if (!cancelled) setEndpointChanges([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [serviceId, endpoint.id]);

  if (loading) {
    return (
      <div className="api-monitor-change__loading">
        <Spin tip="加载变更记录...">
          <div style={{ minHeight: 48 }} />
        </Spin>
      </div>
    );
  }

  return (
    <div className="api-monitor-change">
      <div className="api-monitor-change__section">
        <Typography.Title level={5}>变更历史</Typography.Title>
        {endpointChanges.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该接口暂无变更记录" />
        ) : (
          <Table
            size="small"
            rowKey="id"
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            dataSource={endpointChanges}
            onRow={(record) => ({
              onDoubleClick: () => openCompare(record),
            })}
            columns={[
              {
                title: '时间',
                width: 170,
                render: (_, record) =>
                  formatBeijingTime(record.scan_run?.scanned_at || record.created_at) ||
                  record.created_at,
              },
              {
                title: '类型',
                dataIndex: 'change_type',
                width: 80,
                render: (value: string) => (
                  <Tag color={CHANGE_TYPE_COLORS[value] || 'default'}>
                    {CHANGE_TYPE_LABELS[value] || value}
                  </Tag>
                ),
              },
              {
                title: 'Commit',
                width: 100,
                render: (_, record) => shortSha(record.scan_run?.commit_sha),
              },
              {
                title: '说明',
                dataIndex: 'summary',
                ellipsis: true,
              },
              {
                title: '对比',
                width: 80,
                render: (_: unknown, record: ApiMonitorEndpointChange) => (
                  <CompareAction onClick={() => openCompare(record)} />
                ),
              },
            ]}
          />
        )}
      </div>

      <ApiMonitorChangeCompareModal
        change={compareChange}
        open={compareOpen}
        onClose={() => {
          setCompareOpen(false);
          setCompareChange(null);
        }}
      />
    </div>
  );
}
