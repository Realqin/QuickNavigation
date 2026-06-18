import { Tag, Tooltip, Typography } from 'antd';
import type { ApiTestCase } from '../types/apiTestCase';

export interface CaseExecuteOutcome {
  pass: boolean;
  reason: string;
  statusCode?: number;
  expectedStatus?: number;
  body?: string;
}

function truncateTooltipBody(body: string, maxLength = 4000): string {
  const text = body.trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}\n...(内容已截断)`;
}

export function buildCaseExecuteOutcome(record: ApiTestCase): CaseExecuteOutcome | null {
  if (record.last_exec_pass == null) {
    return null;
  }

  return {
    pass: record.last_exec_pass,
    reason: record.last_exec_detail || '',
    statusCode: record.last_exec_status_code ?? undefined,
    expectedStatus: record.expected_status,
    body: record.last_exec_response ?? undefined,
  };
}

export function renderCaseExecuteOutcomeTooltip(outcome: CaseExecuteOutcome) {
  if (outcome.statusCode == null && !outcome.body && !outcome.reason) {
    return '无执行详情';
  }

  return (
    <div className="api-monitor-cases__outcome-tooltip">
      {outcome.statusCode != null ? (
        <div className="api-monitor-cases__outcome-tooltip-row">
          <span className="api-monitor-cases__outcome-tooltip-label">状态码</span>
          <span>{outcome.statusCode}</span>
        </div>
      ) : null}
      {outcome.expectedStatus != null && outcome.statusCode != null ? (
        <div className="api-monitor-cases__outcome-tooltip-row">
          <span className="api-monitor-cases__outcome-tooltip-label">预期状态码</span>
          <span>{outcome.expectedStatus}</span>
        </div>
      ) : null}
      {outcome.body != null || outcome.statusCode != null ? (
        <div className="api-monitor-cases__outcome-tooltip-section">
          <div className="api-monitor-cases__outcome-tooltip-label">返回内容</div>
          <pre className="api-monitor-cases__outcome-tooltip-body">
            {truncateTooltipBody(outcome.body || '（空响应）')}
          </pre>
        </div>
      ) : null}
      {!outcome.pass && outcome.reason ? (
        <div className="api-monitor-cases__outcome-tooltip-note">{outcome.reason}</div>
      ) : null}
    </div>
  );
}

export function renderCaseExecuteStatusCell(record: ApiTestCase) {
  const outcome = buildCaseExecuteOutcome(record);
  if (!outcome) {
    return <Typography.Text type="secondary">-</Typography.Text>;
  }

  const tag = outcome.pass ? (
    <Tag color="success" style={{ cursor: 'help' }}>
      通过
    </Tag>
  ) : (
    <Tag color="error" style={{ cursor: 'help' }}>
      不通过
    </Tag>
  );

  if (outcome.statusCode == null && outcome.body == null) {
    return outcome.pass ? tag : <Tooltip title={outcome.reason || '执行未通过'}>{tag}</Tooltip>;
  }

  return (
    <Tooltip
      overlayClassName="api-monitor-cases__outcome-tooltip-overlay"
      title={renderCaseExecuteOutcomeTooltip(outcome)}
    >
      {tag}
    </Tooltip>
  );
}

export function formatProxyResponseBody(body: string): string {
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}
