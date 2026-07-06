import { CheckOutlined, ReloadOutlined } from '@ant-design/icons';
import { App, Button, Drawer, Empty, List, Modal, Space, Spin, Tag, Typography } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  fetchK8sAlarmEvents,
  markK8sAlarmEventRead,
  markK8sAlarmEventsReadAll,
} from '../api';
import K8sAlarmDetailContent, { type K8sAlarmDetailData } from './K8sAlarmDetailContent';
import K8sServiceNameLink from './K8sServiceNameLink';
import { useK8sClusterById } from '../hooks/useK8sClusterById';
import type { K8sAlarmEvent } from '../types/k8s';
import { formatDateTime } from '../utils/dateTime';

interface K8sAlarmNotifyDrawerProps {
  open: boolean;
  clusterId: number | null;
  onClose: () => void;
  onUnreadChange?: (count: number) => void;
  refreshToken?: number;
}

function getErrorMessage(error: unknown, fallback: string) {
  return (
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback
  );
}

function alertTypeLabel(type: K8sAlarmEvent['alert_type']) {
  if (type === 'restart') return '重启';
  if (type === 'exception') return '异常';
  return 'Watermark';
}

function statusTag(status: K8sAlarmEvent['status']) {
  if (status === 'firing') {
    return <Tag color="error">告警中</Tag>;
  }
  return <Tag color="success">已恢复</Tag>;
}

function toDetailData(event: K8sAlarmEvent): K8sAlarmDetailData {
  return {
    title: event.title,
    alert_type: event.alert_type,
    status: event.status,
    namespace: event.namespace,
    service_name: event.service_name,
    occurred_at: event.occurred_at,
    summary: event.summary,
    payload: event.payload,
  };
}

export default function K8sAlarmNotifyDrawer({
  open,
  clusterId,
  onClose,
  onUnreadChange,
  refreshToken = 0,
}: K8sAlarmNotifyDrawerProps) {
  const { message } = App.useApp();
  const cluster = useK8sClusterById(clusterId);
  const [events, setEvents] = useState<K8sAlarmEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const [detailEvent, setDetailEvent] = useState<K8sAlarmEvent | null>(null);

  const syncUnread = useCallback(
    (list: K8sAlarmEvent[]) => {
      const unread = list.filter((item) => item.status === 'firing' && !item.is_read).length;
      onUnreadChange?.(unread);
    },
    [onUnreadChange],
  );

  const loadEvents = useCallback(async () => {
    if (!clusterId) {
      setEvents([]);
      syncUnread([]);
      return;
    }
    setLoading(true);
    try {
      const list = await fetchK8sAlarmEvents(clusterId, { limit: 100 });
      setEvents(list);
      syncUnread(list);
    } catch (error) {
      message.error(getErrorMessage(error, '加载报警消息失败'));
    } finally {
      setLoading(false);
    }
  }, [clusterId, message, syncUnread]);

  useEffect(() => {
    if (!open) {
      return;
    }
    loadEvents().catch(() => undefined);
  }, [open, loadEvents, refreshToken]);

  const handleMarkRead = async (event: K8sAlarmEvent) => {
    if (event.is_read) {
      return;
    }
    try {
      const updated = await markK8sAlarmEventRead(event.id);
      setEvents((prev) => {
        const next = prev.map((item) => (item.id === updated.id ? updated : item));
        syncUnread(next);
        return next;
      });
      setDetailEvent((prev) => (prev?.id === updated.id ? updated : prev));
    } catch (error) {
      message.error(getErrorMessage(error, '标记已读失败'));
    }
  };

  const handleMarkAllRead = async () => {
    if (!clusterId) {
      return;
    }
    setMarkingAll(true);
    try {
      await markK8sAlarmEventsReadAll(clusterId);
      await loadEvents();
      message.success('已全部标记为已读');
    } catch (error) {
      message.error(getErrorMessage(error, '全部已读失败'));
    } finally {
      setMarkingAll(false);
    }
  };

  return (
    <Drawer
      title="站内报警"
      open={open}
      onClose={onClose}
      width={520}
      destroyOnHidden
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            size="small"
            loading={loading}
            onClick={() => {
              loadEvents().catch(() => undefined);
            }}
          >
            刷新
          </Button>
          <Button
            icon={<CheckOutlined />}
            size="small"
            loading={markingAll}
            disabled={!events.some((item) => item.status === 'firing' && !item.is_read)}
            onClick={() => {
              handleMarkAllRead().catch(() => undefined);
            }}
          >
            全部已读
          </Button>
        </Space>
      }
    >
      {loading && !events.length ? (
        <div className="k8s-alarm-notify-drawer__loading">
          <Spin />
        </div>
      ) : events.length ? (
        <List
          className="k8s-alarm-notify-drawer__list"
          dataSource={events}
          renderItem={(item) => (
            <List.Item
              className={
                item.status === 'firing' && !item.is_read
                  ? 'k8s-alarm-notify-drawer__item k8s-alarm-notify-drawer__item--unread'
                  : 'k8s-alarm-notify-drawer__item'
              }
              onClick={() => setDetailEvent(item)}
              actions={[
                !item.is_read ? (
                  <Button
                    key="read"
                    type="link"
                    size="small"
                    onClick={(event) => {
                      event.stopPropagation();
                      handleMarkRead(item).catch(() => undefined);
                    }}
                  >
                    标记已读
                  </Button>
                ) : null,
              ].filter(Boolean)}
            >
              <List.Item.Meta
                title={
                  <Space size={8} wrap>
                    <Typography.Text strong={!item.is_read}>{item.title}</Typography.Text>
                    {statusTag(item.status)}
                    <Tag>{alertTypeLabel(item.alert_type)}</Tag>
                  </Space>
                }
                description={
                  <div className="k8s-alarm-notify-drawer__meta">
                    <Typography.Text type="secondary">
                      {item.namespace} /{' '}
                      <K8sServiceNameLink
                        cluster={cluster}
                        namespace={item.namespace}
                        serviceName={item.service_name}
                        payload={item.payload}
                      />
                    </Typography.Text>
                    {item.summary ? (
                      <Typography.Paragraph className="k8s-alarm-notify-drawer__summary">
                        {item.summary}
                      </Typography.Paragraph>
                    ) : null}
                    <Typography.Text type="secondary" className="k8s-alarm-notify-drawer__time">
                      {formatDateTime(item.occurred_at)}
                      {item.resolved_at ? ` · 恢复于 ${formatDateTime(item.resolved_at)}` : ''}
                    </Typography.Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty description="暂无报警消息" />
      )}

      <Modal
        title={detailEvent?.title ?? '告警详情'}
        open={Boolean(detailEvent)}
        onCancel={() => setDetailEvent(null)}
        footer={
          detailEvent && !detailEvent.is_read ? (
            <Button
              type="primary"
              onClick={() => {
                handleMarkRead(detailEvent).catch(() => undefined);
              }}
            >
              标记已读
            </Button>
          ) : null
        }
        width={720}
        destroyOnHidden
      >
        {detailEvent ? (
          <K8sAlarmDetailContent data={toDetailData(detailEvent)} cluster={cluster} />
        ) : null}
      </Modal>
    </Drawer>
  );
}
