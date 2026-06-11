import {
  DatabaseOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import {
  Button,
  Form,
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
  fetchLogs,
  fetchPublicConfig,
  fetchSubscriptions,
  updateSubscription,
} from '../api';
import CommitAiAnalysisModal from '../components/CommitAiAnalysisModal';
import CommitDiffModal from '../components/CommitDiffModal';
import RepoAccessSettingsModal from '../components/RepoAccessSettingsModal';
import SchemaChangeModal from '../components/SchemaChangeModal';
import SchemaMonitorModal from '../components/SchemaMonitorModal';
import { useDictGroup } from '../hooks/useDict';
import type { ActivityLog, GitlabSubscriptionTree } from '../types';
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
  name: string;
  project_display?: string;
  environment_display?: string;
  connection_type_name?: string | null;
  url?: string;
  branch?: string;
  enabled?: boolean;
  link_key?: string;
  isConnection: boolean;
  children?: SubscriptionTableRow[];
}

function extractCommitSha(log: ActivityLog): string | null {
  const sha = log.payload?.commit_sha;
  return typeof sha === 'string' && sha ? sha : null;
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

function buildTreeRows(trees: GitlabSubscriptionTree[]): SubscriptionTableRow[] {
  return trees.map((tree) => {
    const mainLink = tree.links.find((link) => link.link_key === 'main');
    const subLinks = tree.links.filter((link) => link.link_key !== 'main');

    return {
      key: `conn-${tree.connection_id}`,
      subscription_id: tree.id,
      name: tree.connection_name,
      project_display: tree.project_display,
      environment_display: tree.environment_display,
      connection_type_name: tree.connection_type_name,
      url: mainLink?.url,
      branch: mainLink?.branch,
      enabled: mainLink?.enabled,
      link_key: mainLink ? 'main' : undefined,
      isConnection: true,
      children: subLinks.map((link) => ({
        key: `${tree.id}-${link.link_key}`,
        subscription_id: tree.id,
        link_key: link.link_key,
        name: link.name,
        url: link.url,
        branch: link.branch,
        enabled: link.enabled,
        isConnection: false,
      })),
    };
  });
}

export default function LogsPage() {
  const { projects, environments } = useDictGroup();
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [subs, setSubs] = useState<GitlabSubscriptionTree[]>([]);
  const [loading, setLoading] = useState(false);
  const [logForm] = Form.useForm();
  const [subForm] = Form.useForm();
  const [diffLogId, setDiffLogId] = useState<number | null>(null);
  const [diffCommitSha, setDiffCommitSha] = useState<string | null>(null);
  const [diffSummary, setDiffSummary] = useState<string | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [aiLogId, setAiLogId] = useState<number | null>(null);
  const [aiCommitSha, setAiCommitSha] = useState<string | null>(null);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [webhookBase, setWebhookBase] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [schemaMonitorOpen, setSchemaMonitorOpen] = useState(false);
  const [schemaMonitorSubId, setSchemaMonitorSubId] = useState<number | null>(null);
  const [schemaMonitorName, setSchemaMonitorName] = useState('');
  const [schemaChangeLog, setSchemaChangeLog] = useState<ActivityLog | null>(null);
  const [schemaChangeOpen, setSchemaChangeOpen] = useState(false);

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
    if (!isSchemaChangeLog(log)) return;
    setSchemaChangeLog(log);
    setSchemaChangeOpen(true);
  };

  const openDiff = (log: ActivityLog) => {
    const sha = extractCommitSha(log);
    if (!sha) return;
    setDiffLogId(log.id);
    setDiffCommitSha(sha);
    setDiffSummary(log.summary ?? null);
    setDiffOpen(true);
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

      <SchemaMonitorModal
        open={schemaMonitorOpen}
        subscriptionId={schemaMonitorSubId}
        connectionName={schemaMonitorName}
        onClose={() => setSchemaMonitorOpen(false)}
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
        defaultExpandAllRows
        scroll={{ x: 1000 }}
        locale={{ emptyText: '暂无 GitLab / 数据库类型连接' }}
        columns={[
          {
            title: '名称',
            dataIndex: 'name',
            width: 160,
            ellipsis: true,
            render: (v: string, record) =>
              record.isConnection ? (
                <Space size={4}>
                  <Typography.Text strong>{v}</Typography.Text>
                  {record.connection_type_name ? (
                    <Tag color="orange">{record.connection_type_name}</Tag>
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
            ellipsis: true,
            render: (v: string | undefined) =>
              v ? (
                <Typography.Text copyable ellipsis={{ tooltip: v }}>
                  {v}
                </Typography.Text>
              ) : null,
          },
          {
            title: '分支',
            dataIndex: 'branch',
            width: 100,
            render: (v: string | undefined) => {
              if (!v || v === '-') return null;
              return <Tag>{v}</Tag>;
            },
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
            width: 110,
            render: (_, record) =>
              record.isConnection && record.connection_type_name?.includes('数据库') ? (
                <Button
                  type="link"
                  size="small"
                  icon={<DatabaseOutlined />}
                  onClick={() => {
                    setSchemaMonitorSubId(record.subscription_id);
                    setSchemaMonitorName(record.name);
                    setSchemaMonitorOpen(true);
                  }}
                >
                  结构巡检
                </Button>
              ) : null,
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

      <SchemaChangeModal
        log={schemaChangeLog}
        open={schemaChangeOpen}
        onClose={() => {
          setSchemaChangeOpen(false);
          setSchemaChangeLog(null);
        }}
      />
      <CommitDiffModal
        logId={diffLogId}
        commitSha={diffCommitSha}
        summary={diffSummary}
        open={diffOpen}
        onClose={() => {
          setDiffOpen(false);
          setDiffLogId(null);
          setDiffCommitSha(null);
          setDiffSummary(null);
        }}
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
    </div>
  );
}
