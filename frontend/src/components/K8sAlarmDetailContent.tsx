import { Descriptions, Empty, Space, Table, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { useMemo } from 'react';
import type { K8sClusterConfig } from '../types/k8s';
import { getRestartMonitorLabel } from '../types/k8s';
import { formatDateTime } from '../utils/dateTime';
import { buildExternalServiceUrl } from '../utils/k8sServiceUrl';
import K8sServiceNameLink from './K8sServiceNameLink';

export interface K8sAlarmDetailData {
  title: string;
  alert_type: 'restart' | 'watermark' | 'exception';
  status: 'firing' | 'resolved';
  namespace: string;
  service_name: string;
  occurred_at: string;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
}

interface RestartPayload {
  restart_monitor?: string;
  restart_count?: number;
  increased_keys?: string[];
  restart_map?: Record<string, number>;
  last_restart_at?: string | null;
}

interface WatermarkValuePayload {
  raw?: string | number | null;
  timestamp?: number | null;
  lag_ms?: number;
}

interface WatermarkOperatorPayload {
  operator_name?: string;
  job_name?: string;
  error?: string;
  watermarks?: WatermarkValuePayload[];
}

interface WatermarkPayload {
  watermark_minutes?: number;
  lag_ms?: number;
  port?: number;
  operators?: WatermarkOperatorPayload[];
}

interface ExceptionEntryPayload {
  exception_name?: string;
  stacktrace?: string;
  timestamp?: number | null;
  task_name?: string;
  location?: string;
}

interface ExceptionJobPayload {
  job_id?: string;
  job_name?: string;
  exception_count?: number;
  latest_timestamp?: number;
  exceptions?: ExceptionEntryPayload[];
}

interface ExceptionPayload {
  port?: number;
  job_id?: string;
  job_name?: string;
  exception?: string;
  exception_timestamp?: number;
  exception_time_beijing?: string;
  exception_count?: number;
  jobs?: ExceptionJobPayload[];
}

interface ExceptionDetailRow {
  key: string;
  jobName: string;
  exceptionName: string;
  timestamp: number | null;
  taskName: string;
}

interface WatermarkDetailRow {
  key: string;
  operator: string;
  job: string;
  raw: string;
  timestamp: number | null;
  lagMs: number;
  error: string;
}

interface RestartRow {
  key: string;
  count: number;
  increased: boolean;
}

export function formatLagDuration(lagMs: number) {
  if (!Number.isFinite(lagMs) || lagMs <= 0) {
    return '-';
  }
  if (lagMs < 60000) {
    return `${Math.floor(lagMs / 1000)} 秒`;
  }
  const minutes = Math.floor(lagMs / 60000);
  const seconds = Math.floor((lagMs % 60000) / 1000);
  if (minutes < 60) {
    return seconds ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`;
  }
  const hours = Math.floor(minutes / 60);
  const remainMinutes = minutes % 60;
  return remainMinutes ? `${hours} 时 ${remainMinutes} 分` : `${hours} 时`;
}

export function formatElapsedFromNow(value?: string | null) {
  if (!value) {
    return null;
  }
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized.replace(/([+-]\d{2})(\d{2})$/, '$1:$2'));
  const ms = date.getTime();
  if (Number.isNaN(ms)) {
    return null;
  }
  const diff = Math.max(0, Date.now() - ms);
  return formatLagDuration(diff);
}

export function formatWatermarkTimestamp(timestamp: number | null | undefined) {
  if (timestamp == null || !Number.isFinite(timestamp)) {
    return '-';
  }
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(timestamp));
  } catch {
    return '-';
  }
}

function statusTag(status: K8sAlarmDetailData['status']) {
  if (status === 'firing') {
    return <Tag color="error">告警中</Tag>;
  }
  return <Tag color="success">已恢复</Tag>;
}

function alertTypeLabel(type: K8sAlarmDetailData['alert_type']) {
  if (type === 'restart') return '重启';
  if (type === 'exception') return '异常';
  return 'Watermark';
}

const watermarkColumns: TableColumnsType<WatermarkDetailRow> = [
  {
    title: '算子',
    width: 200,
    render: (_, row) => (
      <Space size={4} direction="vertical" style={{ gap: 0 }}>
        <Typography.Text strong>{row.operator}</Typography.Text>
        {row.job ? <Typography.Text type="secondary">{row.job}</Typography.Text> : null}
        {row.error ? <Typography.Text type="danger">{row.error}</Typography.Text> : null}
      </Space>
    ),
  },
  {
    title: 'Watermark 原始值',
    width: 180,
    render: (_, row) => <Typography.Text code>{row.raw}</Typography.Text>,
  },
  {
    title: 'Watermark 时间点',
    width: 200,
    render: (_, row) => formatWatermarkTimestamp(row.timestamp),
  },
  {
    title: '与当前差值',
    width: 140,
    render: (_, row) => (
      <Typography.Text type={row.lagMs > 0 ? 'danger' : undefined}>
        {formatLagDuration(row.lagMs)}
      </Typography.Text>
    ),
  },
];

const restartColumns: TableColumnsType<RestartRow> = [
  {
    title: '容器 / Pod 键',
    dataIndex: 'key',
    render: (_, row) => (
      <Space size={4} wrap>
        <Typography.Text code>{row.key}</Typography.Text>
        {row.increased ? <Tag color="error">本次重启</Tag> : null}
      </Space>
    ),
  },
  {
    title: '累计重启次数',
    dataIndex: 'count',
    width: 140,
    render: (_, row) => (
      <Typography.Text strong type={row.count > 0 ? 'danger' : undefined}>
        {row.count}
      </Typography.Text>
    ),
  },
];

const exceptionColumns: TableColumnsType<ExceptionDetailRow> = [
  {
    title: '作业',
    width: 180,
    render: (_, row) => (
      <Space size={4} direction="vertical" style={{ gap: 0 }}>
        <Typography.Text strong>{row.jobName || '-'}</Typography.Text>
        {row.taskName ? <Typography.Text type="secondary">{row.taskName}</Typography.Text> : null}
      </Space>
    ),
  },
  {
    title: '异常名称',
    render: (_, row) => (
      <Typography.Text type="danger" style={{ wordBreak: 'break-all' }}>
        {row.exceptionName || '-'}
      </Typography.Text>
    ),
  },
  {
    title: '异常时间',
    width: 200,
    render: (_, row) => formatWatermarkTimestamp(row.timestamp),
  },
];

export default function K8sAlarmDetailContent({
  data,
  cluster = null,
}: {
  data: K8sAlarmDetailData;
  cluster?: K8sClusterConfig | null;
}) {
  const restartPayload = (data.payload as RestartPayload | undefined) ?? null;
  const watermarkPayload = (data.payload as WatermarkPayload | undefined) ?? null;
  const exceptionPayload = (data.payload as ExceptionPayload | undefined) ?? null;

  const watermarkRows = useMemo<WatermarkDetailRow[]>(() => {
    const operators = watermarkPayload?.operators ?? [];
    const rows: WatermarkDetailRow[] = [];
    operators.forEach((operator, opIndex) => {
      const watermarks = operator.watermarks?.length ? operator.watermarks : [null];
      watermarks.forEach((watermark, wmIndex) => {
        rows.push({
          key: `${opIndex}:${wmIndex}`,
          operator: operator.operator_name || '-',
          job: operator.job_name || '-',
          raw: watermark?.raw != null ? String(watermark.raw) : '-',
          timestamp: watermark?.timestamp ?? null,
          lagMs: watermark?.lag_ms ?? 0,
          error: operator.error || '',
        });
      });
    });
    return rows;
  }, [watermarkPayload]);

  const restartRows = useMemo<RestartRow[]>(() => {
    const restartMap = restartPayload?.restart_map ?? {};
    const increased = new Set(restartPayload?.increased_keys ?? []);
    return Object.entries(restartMap)
      .map(([key, count]) => ({ key, count, increased: increased.has(key) }))
      .sort((a, b) => Number(b.increased) - Number(a.increased) || a.key.localeCompare(b.key));
  }, [restartPayload]);

  const exceptionRows = useMemo<ExceptionDetailRow[]>(() => {
    const jobs = exceptionPayload?.jobs ?? [];
    const rows: ExceptionDetailRow[] = [];
    jobs.forEach((job, jobIndex) => {
      const entries = job.exceptions?.length ? job.exceptions : [null];
      entries.forEach((entry, entryIndex) => {
        rows.push({
          key: `${jobIndex}:${entryIndex}`,
          jobName: job.job_name || '',
          exceptionName: entry?.exception_name || '',
          timestamp: entry?.timestamp ?? null,
          taskName: entry?.task_name || '',
        });
      });
    });
    return rows;
  }, [exceptionPayload]);

  const flinkPort = useMemo(() => {
    const portValue = watermarkPayload?.port ?? exceptionPayload?.port;
    return typeof portValue === 'number' ? portValue : null;
  }, [exceptionPayload?.port, watermarkPayload?.port]);

  const flinkUrl = useMemo(
    () => buildExternalServiceUrl(cluster, flinkPort),
    [cluster, flinkPort],
  );

  const renderFlinkPort = () => {
    if (flinkPort == null) {
      return '-';
    }
    if (flinkUrl) {
      return (
        <a
          href={flinkUrl}
          target="_blank"
          rel="noreferrer"
          className="k8s-service-name-link"
          title="打开 Flink 控制台"
        >
          {flinkPort}
        </a>
      );
    }
    return flinkPort;
  };

  return (
    <div className="k8s-alarm-notify-drawer__detail">
      <Space size={8} wrap style={{ marginBottom: 12 }}>
        {statusTag(data.status)}
        <Tag>{alertTypeLabel(data.alert_type)}</Tag>
        <Typography.Text type="secondary">
          {data.namespace} /{' '}
          <K8sServiceNameLink
            cluster={cluster}
            namespace={data.namespace}
            serviceName={data.service_name}
            payload={data.payload}
          />
        </Typography.Text>
        {flinkUrl ? (
          <Typography.Link href={flinkUrl} target="_blank" rel="noreferrer">
            打开控制台
          </Typography.Link>
        ) : null}
      </Space>

      {data.alert_type === 'restart' ? (
        <>
          <Descriptions
            size="small"
            column={1}
            bordered
            labelStyle={{ width: 140 }}
            items={[
              {
                key: 'rule',
                label: '重启监控规则',
                children: getRestartMonitorLabel(restartPayload?.restart_monitor ?? 'none'),
              },
              {
                key: 'count',
                label: '累计重启次数',
                children: restartPayload?.restart_count ?? '-',
              },
              {
                key: 'last',
                label: '上次重启时间',
                children: (
                  <Space size={8} wrap>
                    <Typography.Text>
                      {formatDateTime(restartPayload?.last_restart_at) || '-'}
                    </Typography.Text>
                    {formatElapsedFromNow(restartPayload?.last_restart_at) ? (
                      <Typography.Text type="secondary">
                        距今 {formatElapsedFromNow(restartPayload?.last_restart_at)}
                      </Typography.Text>
                    ) : null}
                  </Space>
                ),
              },
              {
                key: 'occurred',
                label: '告警触发时间',
                children: formatDateTime(data.occurred_at) || '-',
              },
            ]}
          />
          {restartRows.length ? (
            <Table
              size="small"
              rowKey="key"
              columns={restartColumns}
              dataSource={restartRows}
              pagination={false}
              scroll={{ y: 240 }}
              style={{ marginTop: 12 }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="无容器重启明细"
              style={{ marginTop: 12 }}
            />
          )}
        </>
      ) : null}

      {data.alert_type === 'watermark' ? (
        <>
          <Descriptions
            size="small"
            column={1}
            bordered
            labelStyle={{ width: 140 }}
            items={[
              {
                key: 'threshold',
                label: '延迟阈值',
                children: watermarkPayload?.watermark_minutes
                  ? `${watermarkPayload.watermark_minutes} 分钟`
                  : '-',
              },
              {
                key: 'port',
                label: 'Flink 端口',
                children: renderFlinkPort(),
              },
              {
                key: 'maxlag',
                label: '最大延迟',
                children: watermarkPayload?.lag_ms
                  ? formatLagDuration(watermarkPayload.lag_ms)
                  : '-',
              },
              {
                key: 'occurred',
                label: '告警触发时间',
                children: formatDateTime(data.occurred_at) || '-',
              },
            ]}
          />
          {watermarkRows.length ? (
            <Table
              size="small"
              rowKey="key"
              columns={watermarkColumns}
              dataSource={watermarkRows}
              pagination={false}
              scroll={{ y: 320 }}
              style={{ marginTop: 12 }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="无 Watermark 算子明细（旧告警未保存明细）"
              style={{ marginTop: 12 }}
            />
          )}
        </>
      ) : null}

      {data.alert_type === 'exception' ? (
        <>
          <Descriptions
            size="small"
            column={1}
            bordered
            labelStyle={{ width: 140 }}
            items={[
              {
                key: 'job',
                label: 'Flink 作业',
                children: exceptionPayload?.job_name || '-',
              },
              {
                key: 'exTime',
                label: '异常时间',
                children: (
                  <Space size={8} wrap>
                    <Typography.Text>
                      {exceptionPayload?.exception_time_beijing ||
                        formatWatermarkTimestamp(exceptionPayload?.exception_timestamp) ||
                        '-'}
                    </Typography.Text>
                    {formatElapsedFromNow(
                      exceptionPayload?.exception_timestamp
                        ? new Date(exceptionPayload.exception_timestamp).toISOString()
                        : null,
                    ) ? (
                      <Typography.Text type="secondary">
                        距今{' '}
                        {formatElapsedFromNow(
                          exceptionPayload?.exception_timestamp
                            ? new Date(exceptionPayload.exception_timestamp).toISOString()
                            : null,
                        )}
                      </Typography.Text>
                    ) : null}
                  </Space>
                ),
              },
              {
                key: 'port',
                label: 'Flink 端口',
                children: renderFlinkPort(),
              },
              {
                key: 'count',
                label: '异常条数',
                children: exceptionPayload?.exception_count ?? '-',
              },
              {
                key: 'occurred',
                label: '告警触发时间',
                children: formatDateTime(data.occurred_at) || '-',
              },
            ]}
          />
          {exceptionPayload?.exception ? (
            <div style={{ marginTop: 12 }}>
              <Typography.Text type="secondary">Root Exception</Typography.Text>
              <Typography.Paragraph
                style={{
                  marginTop: 4,
                  marginBottom: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  maxHeight: 240,
                  overflow: 'auto',
                  padding: 8,
                  background: 'rgba(255,77,79,0.06)',
                  border: '1px solid rgba(255,77,79,0.25)',
                  borderRadius: 6,
                }}
                copyable={{ text: exceptionPayload.exception }}
              >
                {exceptionPayload.exception}
              </Typography.Paragraph>
            </div>
          ) : null}
          {exceptionRows.length ? (
            <Table
              size="small"
              rowKey="key"
              columns={exceptionColumns}
              dataSource={exceptionRows}
              pagination={false}
              scroll={{ y: 320 }}
              style={{ marginTop: 12 }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="无作业异常明细"
              style={{ marginTop: 12 }}
            />
          )}
        </>
      ) : null}

      {data.summary ? (
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
          {data.summary}
        </Typography.Paragraph>
      ) : null}
    </div>
  );
}
