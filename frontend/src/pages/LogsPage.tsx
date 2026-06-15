import {
  DatabaseOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { AxiosError } from 'axios';
import {
  Button,
  Form,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchConnection,
  fetchLogs,
  fetchPublicConfig,
  fetchSubscriptions,
  scanSchemaMonitor,
  updateConnection,
  updateSubscription,
} from '../api';
import CommitAiAnalysisModal from '../components/CommitAiAnalysisModal';
import ConnectionFormModal from '../components/ConnectionFormModal';
import RepoAccessSettingsModal from '../components/RepoAccessSettingsModal';
import { useDictGroup } from '../hooks/useDict';
import { useActivityLogDetail } from '../hooks/useActivityLogDetail';
import type { ActivityLog, Connection, ConnectionFormValues, GitlabSubscriptionTree } from '../types';
import { extractCommitSha } from '../utils/activityLogDetail';
import { formatBeijingTime } from '../utils/dateTime';
import { getSchemaChanges, isSchemaChangeLog } from '../utils/schemaChangeLog';

const ENABLED_FILTER_OPTIONS = [
  { label: '已启用', value: true },
  { label: '未启用', value: false },
];

const LOGS_PAGE_HINT = '只获取类型为 GitLab 和数据库类型的数据';

interface SubscriptionTableRow {
  key: string;
  subscription_id: number;
  connection_id: number;
  name: string;
  project_display?: string;
  environment_display?: string;
  connection_type_name?: string | null;
  url?: string;
  branch?: string;
  updated_at?: string | null;
  enabled?: boolean;
  link_key?: string;
  isConnection: boolean;
  children?: SubscriptionTableRow[];
}

function extractCommitTime(log: ActivityLog): string | null {
  const committedAt = log.payload?.committed_at;
  if (typeof committedAt === 'string' && committedAt) {
    const formatted = formatBeijingTime(committedAt.trim().replace(/ UTC$/, 'Z'));
    if (formatted) {
      return formatted;
    }
  }
  if (log.source_type !== 'database') {
    return null;
  }
  return formatBeijingTime(log.occurred_at);
}

function renderActor(log: ActivityLog): string | null {
  if (log.author) {
    return log.author === 'schema-monitor' ? '结构巡检' : log.author;
  }
  if (log.source_type === 'database') {
    const actor = log.payload?.actor ?? log.payload?.user ?? log.payload?.ip;
    if (typeof actor === 'string' && actor.trim()) {
      return actor;
    }
    return '未知';
  }
  return null;
}

function pickLatestTime(...times: Array<string | null | undefined>): string | null {
  let latest: string | null = null;
  for (const time of times) {
    if (!time) continue;
    if (!latest || new Date(time).getTime() > new Date(latest).getTime()) {
      latest = time;
    }
  }
  return latest;
}

function resolveConnectionUpdatedAt(
  mainUpdatedAt: string | null | undefined,
  children: SubscriptionTableRow[] | undefined,
): string | null {
  if (mainUpdatedAt) {
    return mainUpdatedAt;
  }
  return pickLatestTime(...(children?.map((child) => child.updated_at) ?? []));
}

function buildTreeRows(trees: GitlabSubscriptionTree[]): SubscriptionTableRow[] {
  return trees.map((tree) => {
    const mainLink = tree.links.find((link) => link.link_key === 'main');
    const subLinks = tree.links.filter((link) => link.link_key !== 'main');

    const row: SubscriptionTableRow = {
      key: `conn-${tree.connection_id}`,
      subscription_id: tree.id,
      connection_id: tree.connection_id,
      name: tree.connection_name,
      project_display: tree.project_display,
      environment_display: tree.environment_display,
      connection_type_name: tree.connection_type_name,
      url: mainLink?.url,
      branch: mainLink?.branch,
      enabled: mainLink?.enabled,
      link_key: mainLink ? 'main' : undefined,
      isConnection: true,
    };

    if (subLinks.length > 0) {
      row.children = subLinks.map((link) => ({
        key: `${tree.id}-${link.link_key}`,
        subscription_id: tree.id,
        connection_id: tree.connection_id,
        link_key: link.link_key,
        name: link.name,
        url: link.url,
        branch: link.branch,
        updated_at: link.last_updated_at ?? null,
        enabled: link.enabled,
        isConnection: false,
      }));
    }

    row.updated_at = resolveConnectionUpdatedAt(
      mainLink?.last_updated_at ?? null,
      row.children,
    );

    return row;
  });
}

function extractScanError(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<{ detail?: string }>;
  const detail = axiosError.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (axiosError.code === 'ECONNABORTED') {
    return '巡检超时，库表较多时请稍候再试或缩小监控范围';
  }
  return fallback;
}

function isDatabaseConnection(typeName?: string | null): boolean {
  return Boolean(typeName?.includes('数据库'));
}

export default function LogsPage() {
  const { projects, environments, labels, connectionGroups } = useDictGroup();
  const { openActivityLogDetail, detailModals } = useActivityLogDetail();
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [subs, setSubs] = useState<GitlabSubscriptionTree[]>([]);
  const [loading, setLoading] = useState(false);
  const [logForm] = Form.useForm();
  const [subForm] = Form.useForm();
  const [aiLogId, setAiLogId] = useState<number | null>(null);
  const [aiCommitSha, setAiCommitSha] = useState<string | null>(null);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [webhookBase, setWebhookBase] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [connectionModalOpen, setConnectionModalOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<Connection | null>(null);
  const [scanningSubIds, setScanningSubIds] = useState<number[]>([]);

  const tableData = useMemo(() => buildTreeRows(subs), [subs]);

  const resolveWebhookBase = useCallback(async () => {
    try {
      const config = await fetchPublicConfig();
      const configured = config.webhook_base_url.trim().replace(/\/$/, '');
      setWebhookBase(configured || window.location.origin);
    } catch {
      setWebhookBase(window.location.origin);
    }
  }, []);

  const loadSubscriptions = useCallback(async () => {
    const filter = subForm.getFieldsValue();
    const list = await fetchSubscriptions({
      project: filter.project,
      enabled: filter.enabled,
    });
    setSubs(list);
  }, [subForm]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const logFilter = logForm.getFieldsValue();
      const logList = await fetchLogs({
        project: logFilter.project || undefined,
        environment: logFilter.environment || undefined,
        source_type: logFilter.source_type || undefined,
        limit: 100,
      });
      setLogs(logList);
      await loadSubscriptions();
    } catch {
      message.error('加载失败');
    } finally {
      setLoading(false);
    }
  }, [logForm, loadSubscriptions]);

  useEffect(() => {
    loadAll();
    resolveWebhookBase();
  }, [loadAll, resolveWebhookBase]);

  const buildWebhookUrl = (path: string) => `${webhookBase.replace(/\/$/, '')}${path}`;

  const copyGitlabWebhook = () => {
    navigator.clipboard.writeText(buildWebhookUrl('/webhooks/gitlab'));
    message.success('GitLab Webhook 地址已复制');
  };

  const formatDictId = (value: string, idMap: Record<number, string>) => {
    const id = Number(value);
    if (Number.isFinite(id)) {
      return idMap[id] ?? value;
    }
    return value;
  };

  const openSchemaChange = (log: ActivityLog) => {
    openActivityLogDetail(log);
  };

  const openDiff = (log: ActivityLog) => {
    openActivityLogDetail(log);
  };

  const openAiAnalysis = (log: ActivityLog) => {
    const sha = extractCommitSha(log);
    if (!sha) return;
    setAiLogId(log.id);
    setAiCommitSha(sha);
    setAiSummary(log.summary ?? null);
    setAiOpen(true);
  };

  const renderCommitLink = (log: ActivityLog) => {
    if (isSchemaChangeLog(log)) {
      return (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => openSchemaChange(log)}>
          {getSchemaChanges(log).length} 项
        </Button>
      );
    }
    const sha = extractCommitSha(log);
    if (!sha) return null;
    return (
      <Button type="link" size="small" style={{ padding: 0 }} onClick={() => openDiff(log)}>
        {sha.slice(0, 7)}
      </Button>
    );
  };

  const renderSummary = (summary: string | null | undefined, log: ActivityLog) => {
    if (!summary) return null;
    if (isSchemaChangeLog(log)) {
      return (
        <Button
          type="link"
          size="small"
          style={{ padding: 0, height: 'auto', whiteSpace: 'normal', textAlign: 'left' }}
          onClick={() => openSchemaChange(log)}
        >
          {summary}
        </Button>
      );
    }
    const sha = extractCommitSha(log);
    if (!sha) return summary;
    return (
      <Button
        type="link"
        size="small"
        style={{ padding: 0, height: 'auto', whiteSpace: 'normal', textAlign: 'left' }}
        onClick={() => openDiff(log)}
      >
        {summary}
      </Button>
    );
  };

  const handleSubFilterChange = () => {
    loadSubscriptions().catch(() => message.error('加载订阅失败'));
  };

  const handleLinkToggle = async (subscriptionId: number, linkKey: string, checked: boolean) => {
    try {
      await updateSubscription(subscriptionId, { link_enabled: { [linkKey]: checked } });
      await loadSubscriptions();
    } catch {
      message.error('更新订阅失败');
    }
  };

  const handleEditConnection = async (connectionId: number) => {
    try {
      const connection = await fetchConnection(connectionId);
      setEditingConnection(connection);
      setConnectionModalOpen(true);
    } catch {
      message.error('加载连接失败');
    }
  };

  const handleConnectionSubmit = async (values: ConnectionFormValues) => {
    if (!editingConnection) return;
    try {
      await updateConnection(editingConnection.id, values);
      message.success('更新成功');
      setConnectionModalOpen(false);
      setEditingConnection(null);
      await loadAll();
    } catch {
      message.error('保存失败');
    }
  };

  const handleImmediateScan = async (record: SubscriptionTableRow) => {
    const hide = message.loading('巡检中，库表较多时可能需要几十秒...', 0);
    setScanningSubIds((prev) => [...prev, record.subscription_id]);
    try {
      const result = await scanSchemaMonitor(record.subscription_id);
      message.success(result.message);
      await loadAll();
    } catch (error) {
      const detail = extractScanError(error, '巡检失败');
      Modal.warning({
        title: '无法立即巡检',
        content: detail,
        okText: '去修改',
        onOk: () => handleEditConnection(record.connection_id),
      });
    } finally {
      hide();
      setScanningSubIds((prev) => prev.filter((id) => id !== record.subscription_id));
    }
  };

  const renderUpdatedAt = (value: string | null | undefined) => {
    if (!value) return null;
    const formatted = formatBeijingTime(value);
    return formatted ? (
      <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        {formatted}
      </Typography.Text>
    ) : null;
  };

  return (
    <div className="tab-page">
      <div className="tab-page-toolbar">
        <Space size={6} align="center">
          <Typography.Title level={5} style={{ margin: 0 }}>
            日志与订阅
          </Typography.Title>
          <Tooltip title={LOGS_PAGE_HINT}>
            <ExclamationCircleOutlined style={{ color: '#faad14', cursor: 'help' }} />
          </Tooltip>
        </Space>
        <Space>
          <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>
            仓库访问配置
          </Button>
          <Button onClick={copyGitlabWebhook}>复制 GitLab Webhook</Button>
          <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <RepoAccessSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={resolveWebhookBase}
      />

      <ConnectionFormModal
        open={connectionModalOpen}
        connection={editingConnection}
        projectOptions={projects.options}
        environmentOptions={environments.options}
        labelOptions={labels.options}
        labelItems={labels.items}
        groupOptions={connectionGroups.options}
        groupItems={connectionGroups.items}
        onCancel={() => {
          setConnectionModalOpen(false);
          setEditingConnection(null);
        }}
        onSubmit={handleConnectionSubmit}
      />

      <Form form={subForm} layout="inline" style={{ marginBottom: 12 }} onValuesChange={handleSubFilterChange}>
        <Form.Item name="project" label="项目">
          <Select allowClear style={{ width: 160 }} placeholder="全部" options={projects.options} />
        </Form.Item>
        <Form.Item name="enabled" label="是否启用">
          <Select allowClear style={{ width: 120 }} placeholder="全部" options={ENABLED_FILTER_OPTIONS} />
        </Form.Item>
      </Form>

      <Table
        rowKey="key"
        size="small"
        loading={loading}
        dataSource={tableData}
        pagination={false}
        style={{ marginBottom: 24 }}
        scroll={{ x: 1280 }}
        expandable={{
          defaultExpandAllRows: true,
          rowExpandable: (record) => (record.children?.length ?? 0) > 0,
        }}
        locale={{ emptyText: '暂无 GitLab / 数据库类型连接' }}
        columns={[
          {
            title: '名称',
            dataIndex: 'name',
            width: 280,
            render: (v: string, record) =>
              record.isConnection ? (
                <Space size={[4, 4]} wrap>
                  <Typography.Text strong>{v}</Typography.Text>
                  {record.connection_type_name ? (
                    <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                      {record.connection_type_name}
                    </Tag>
                  ) : null}
                </Space>
              ) : (
                <Typography.Text type="secondary">{v}</Typography.Text>
              ),
          },
          {
            title: '项目',
            dataIndex: 'project_display',
            width: 100,
            ellipsis: true,
            render: (v: string | undefined, record) =>
              record.isConnection ? v || '共用' : null,
          },
          {
            title: '环境',
            dataIndex: 'environment_display',
            width: 100,
            ellipsis: true,
            render: (v: string | undefined, record) =>
              record.isConnection ? v || null : null,
          },
          {
            title: '地址',
            dataIndex: 'url',
            width: 220,
            render: (v: string | undefined) =>
              v ? (
                <Typography.Text
                  copyable
                  style={{ fontSize: 12, wordBreak: 'break-all', whiteSpace: 'normal' }}
                >
                  {v}
                </Typography.Text>
              ) : null,
          },
          {
            title: '分支',
            dataIndex: 'branch',
            width: 88,
            render: (v: string | undefined) => {
              if (!v || v === '-') return null;
              return <Tag>{v}</Tag>;
            },
          },
          {
            title: '更新时间',
            dataIndex: 'updated_at',
            width: 156,
            render: (v: string | null | undefined) => renderUpdatedAt(v),
          },
          {
            title: '启用',
            width: 72,
            render: (_, record) =>
              record.link_key ? (
                <Switch
                  checked={!!record.enabled}
                  onChange={(checked) =>
                    handleLinkToggle(record.subscription_id, record.link_key!, checked)
                  }
                />
              ) : null,
          },
          {
            title: '操作',
            width: 168,
            fixed: 'right',
            render: (_, record) => {
              if (!record.isConnection) return null;
              return (
                <Space size={6} wrap={false} style={{ whiteSpace: 'nowrap' }}>
                  <Button
                    type="link"
                    size="small"
                    icon={<EditOutlined />}
                    style={{ paddingInline: 0 }}
                    onClick={() => handleEditConnection(record.connection_id)}
                  >
                    编辑
                  </Button>
                  {isDatabaseConnection(record.connection_type_name) ? (
                    <Button
                      type="link"
                      size="small"
                      icon={<DatabaseOutlined />}
                      style={{ paddingInline: 0 }}
                      loading={scanningSubIds.includes(record.subscription_id)}
                      onClick={() => handleImmediateScan(record)}
                    >
                      立即巡检
                    </Button>
                  ) : null}
                </Space>
              );
            },
          },
        ]}
      />

      <Typography.Title level={5}>活动日志</Typography.Title>
      <Form form={logForm} layout="inline" style={{ marginBottom: 16 }} onFinish={loadAll}>
        <Form.Item name="project" label="项目">
          <Select allowClear style={{ width: 160 }} placeholder="项目" options={projects.options} />
        </Form.Item>
        <Form.Item name="environment" label="环境">
          <Select allowClear style={{ width: 140 }} placeholder="环境" options={environments.options} />
        </Form.Item>
        <Form.Item name="source_type" label="来源">
          <Select
            allowClear
            style={{ width: 120 }}
            placeholder="来源"
            options={[
              { label: 'GitLab', value: 'gitlab' },
              { label: '数据库', value: 'database' },
            ]}
          />
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
        scroll={{ x: 1100 }}
        columns={[
          {
            title: '项目',
            dataIndex: 'project',
            width: 100,
            render: (v: string) => formatDictId(v, projects.idMap),
          },
          {
            title: '环境',
            dataIndex: 'environment',
            width: 100,
            render: (v: string) => formatDictId(v, environments.idMap),
          },
          {
            title: '来源',
            dataIndex: 'source_type',
            width: 90,
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: '变更项',
            width: 100,
            render: (_, record) => renderCommitLink(record),
          },
          {
            title: '摘要',
            dataIndex: 'summary',
            ellipsis: true,
            render: (v: string | null | undefined, record) => renderSummary(v, record),
          },
          {
            title: '分支',
            width: 100,
            render: (_, record) => {
              const branch = record.payload?.branch;
              return typeof branch === 'string' ? branch : null;
            },
          },
          {
            title: '操作者',
            width: 100,
            ellipsis: true,
            render: (_, record) => renderActor(record),
          },
          {
            title: '时间',
            width: 170,
            render: (_, record) => extractCommitTime(record),
          },
          {
            title: '操作',
            width: 90,
            fixed: 'right',
            render: (_, record) => {
              const sha = extractCommitSha(record);
              if (!sha) return null;
              return (
                <Button type="link" size="small" style={{ padding: 0 }} onClick={() => openAiAnalysis(record)}>
                  AI 分析
                </Button>
              );
            },
          },
        ]}
      />

      <CommitAiAnalysisModal
        logId={aiLogId}
        commitSha={aiCommitSha}
        summary={aiSummary}
        open={aiOpen}
        onClose={() => {
          setAiOpen(false);
          setAiLogId(null);
          setAiCommitSha(null);
          setAiSummary(null);
        }}
      />
      {detailModals}
    </div>
  );
}
