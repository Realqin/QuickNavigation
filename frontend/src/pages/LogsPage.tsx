import { CopyOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createSubscription,
  fetchConnections,
  fetchLogs,
  fetchSubscriptions,
  updateSubscription,
} from '../api';
import { useDictGroup } from '../hooks/useDict';
import type { ActivityLog, Connection, Subscription } from '../types';

const SOURCE_TYPE_OPTIONS = [
  { label: 'GitHub', value: 'github' },
  { label: '数据库', value: 'database' },
];

export default function LogsPage() {
  const { projects, environments, labels } = useDictGroup();
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const filter = form.getFieldsValue();
      const [logList, subList, connList] = await Promise.all([
        fetchLogs({
          project: filter.project || undefined,
          environment: filter.environment || undefined,
          source_type: filter.source_type || undefined,
          limit: 100,
        }),
        fetchSubscriptions(),
        fetchConnections(),
      ]);
      setLogs(logList);
      setSubs(subList);
      setConnections(connList);
    } catch {
      message.error('加载失败');
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const subscribableConnections = useMemo(
    () => connections.filter((c) => !subs.some((s) => s.connection_id === c.id)),
    [connections, subs],
  );

  const handleCreateSub = async (connectionId: number) => {
    const conn = connections.find((c) => c.id === connectionId);
    if (!conn) return;
    const isGithub = /github\.com/i.test(conn.url);
    try {
      await createSubscription({
        connection_id: connectionId,
        enabled: true,
        github_repo: isGithub ? extractGithubRepo(conn.url) : undefined,
        github_events: isGithub ? ['push', 'pull_request'] : undefined,
      });
      message.success('订阅已创建');
      loadAll();
    } catch {
      message.error('创建订阅失败');
    }
  };

  const copyWebhook = (secret: string) => {
    const url = `${window.location.origin}/webhooks/database?secret=${secret}`;
    navigator.clipboard.writeText(url);
    message.success('Webhook 地址已复制');
  };

  const formatDictId = (value: string, idMap: Record<number, string>) => {
    const id = Number(value);
    if (Number.isFinite(id)) {
      return idMap[id] ?? value;
    }
    return value;
  };

  return (
    <div className="tab-page">
      <div className="tab-page-toolbar">
        <Typography.Title level={5} style={{ margin: 0 }}>
          日志与订阅
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>
          刷新
        </Button>
      </div>

      <Typography.Title level={5}>订阅配置</Typography.Title>
      <Space style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 280 }}
          placeholder="选择连接创建订阅"
          options={subscribableConnections.map((c) => ({
            label: `${c.name} (${labels.idMap[c.type] ?? c.type})`,
            value: c.id,
          }))}
          onSelect={handleCreateSub}
          value={null}
        />
      </Space>

      <Table
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={subs}
        pagination={false}
        style={{ marginBottom: 24 }}
        columns={[
          {
            title: '连接',
            render: (_, record) => {
              const conn = connections.find((c) => c.id === record.connection_id);
              if (!conn) return record.connection_id;
              const projectText = (conn.projects ?? [])
                .map((id) => projects.idMap[id] ?? id)
                .join(', ');
              const envText = (conn.environments ?? [])
                .map((id) => environments.idMap[id] ?? id)
                .join(', ');
              return `${conn.name} (${projectText}/${envText})`;
            },
          },
          { title: 'GitHub 仓库', dataIndex: 'github_repo', render: (v) => v || '-' },
          {
            title: '启用',
            dataIndex: 'enabled',
            render: (enabled: boolean, record) => (
              <Switch
                checked={enabled}
                onChange={async (checked) => {
                  await updateSubscription(record.id, { enabled: checked });
                  loadAll();
                }}
              />
            ),
          },
          {
            title: 'Webhook',
            render: (_, record) => (
              <Button size="small" icon={<CopyOutlined />} onClick={() => copyWebhook(record.webhook_secret)}>
                复制 DB Webhook
              </Button>
            ),
          },
        ]}
      />

      <Typography.Title level={5}>活动日志</Typography.Title>
      <Form form={form} layout="inline" style={{ marginBottom: 16 }} onFinish={loadAll}>
        <Form.Item name="project" label="项目">
          <Select allowClear style={{ width: 160 }} placeholder="项目" options={projects.options} />
        </Form.Item>
        <Form.Item name="environment" label="环境">
          <Select allowClear style={{ width: 140 }} placeholder="环境" options={environments.options} />
        </Form.Item>
        <Form.Item name="source_type" label="来源">
          <Select allowClear style={{ width: 160 }} placeholder="来源" options={SOURCE_TYPE_OPTIONS} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">
            筛选
          </Button>
        </Form.Item>
      </Form>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={logs}
        pagination={{ pageSize: 15 }}
        columns={[
          { title: '标题', dataIndex: 'title', ellipsis: true },
          { title: '摘要', dataIndex: 'summary', ellipsis: true },
          {
            title: '来源',
            dataIndex: 'source_type',
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: '项目',
            dataIndex: 'project',
            render: (v: string) => formatDictId(v, projects.idMap),
          },
          {
            title: '环境',
            dataIndex: 'environment',
            render: (v: string) => formatDictId(v, environments.idMap),
          },
          { title: '作者', dataIndex: 'author' },
          {
            title: '时间',
            dataIndex: 'occurred_at',
            render: (v: string) => new Date(v).toLocaleString(),
          },
        ]}
      />
    </div>
  );
}

function extractGithubRepo(url: string): string | undefined {
  try {
    const u = new URL(url);
    const parts = u.pathname.split('/').filter(Boolean);
    if (parts.length >= 2) return `${parts[0]}/${parts[1]}`;
  } catch {
    return undefined;
  }
  return undefined;
}
