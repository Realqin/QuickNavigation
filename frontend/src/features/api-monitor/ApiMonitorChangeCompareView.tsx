import { Tag, Typography } from 'antd';
import type { ApiMonitorEndpointChange } from '../../types/apiMonitor';
import {
  buildDiffSummaryItems,
  buildEndpointCompareColumns,
  type HighlightedText,
  type SnapshotCompareSide,
} from './formatEndpointChange';

interface ApiMonitorChangeCompareViewProps {
  change: ApiMonitorEndpointChange;
}

function highlightClassName(highlight: HighlightedText['highlight']): string {
  if (highlight === 'removed') return 'api-monitor-compare__highlight--removed';
  if (highlight === 'added') return 'api-monitor-compare__highlight--added';
  return '';
}

function HighlightedValue({ item }: { item: HighlightedText }) {
  const className = highlightClassName(item.highlight);
  if (item.text.includes('\n') || item.text.length > 120) {
    return <div className={`api-monitor-compare__value ${className}`.trim()}>{item.text}</div>;
  }
  return (
    <Typography.Text code={!className} className={`api-monitor-compare__value ${className}`.trim()}>
      {item.text}
    </Typography.Text>
  );
}

function HighlightedList({ items }: { items: HighlightedText[] }) {
  return (
    <ul className="api-monitor-compare__list">
      {items.map((item, index) => (
        <li
          key={`${item.text}-${index}`}
          className={`api-monitor-compare__list-item ${highlightClassName(item.highlight)}`.trim()}
        >
          {item.text}
        </li>
      ))}
    </ul>
  );
}

function SnapshotColumn({
  title,
  tone,
  blocks,
  emptyText,
}: {
  title: string;
  tone: 'before' | 'after';
  blocks: SnapshotCompareSide | null;
  emptyText: string;
}) {
  return (
    <div className={`api-monitor-compare__column api-monitor-compare__column--${tone}`}>
      <div className={`api-monitor-compare__column-head api-monitor-compare__column-head--${tone}`}>
        {title}
      </div>
      {!blocks ? (
        <Typography.Text type="secondary" className="api-monitor-compare__empty">
          {emptyText}
        </Typography.Text>
      ) : (
        <div className="api-monitor-compare__content">
          <section className="api-monitor-compare__block">
            <Typography.Text strong className="api-monitor-compare__label">
              接口
            </Typography.Text>
            <HighlightedValue item={blocks.title} />
          </section>
          <section className="api-monitor-compare__block">
            <Typography.Text strong className="api-monitor-compare__label">
              摘要
            </Typography.Text>
            <HighlightedValue item={blocks.summary} />
          </section>
          <section className="api-monitor-compare__block">
            <Typography.Text strong className="api-monitor-compare__label">
              请求类型
            </Typography.Text>
            <HighlightedValue item={blocks.requestContentType} />
          </section>
          <section className="api-monitor-compare__block">
            <Typography.Text strong className="api-monitor-compare__label">
              响应类型
            </Typography.Text>
            <HighlightedValue item={blocks.responseContentType} />
          </section>
          <section className="api-monitor-compare__block">
            <Typography.Text strong className="api-monitor-compare__label">
              参数
            </Typography.Text>
            <HighlightedList items={blocks.parameters} />
          </section>
          <section className="api-monitor-compare__block">
            <Typography.Text strong className="api-monitor-compare__label">
              响应
            </Typography.Text>
            <HighlightedList items={blocks.responses} />
          </section>
        </div>
      )}
    </div>
  );
}

const CHANGE_TYPE_LABELS: Record<string, string> = {
  added: '新增',
  modified: '修改',
  removed: '删除',
};

const CHANGE_TYPE_COLORS: Record<string, string> = {
  added: 'green',
  modified: 'blue',
  removed: 'red',
};

const DIFF_SUMMARY_CLASS: Record<string, string> = {
  added: 'api-monitor-compare__diff-item--added',
  removed: 'api-monitor-compare__diff-item--removed',
  modified: 'api-monitor-compare__diff-item--modified',
};

export default function ApiMonitorChangeCompareView({ change }: ApiMonitorChangeCompareViewProps) {
  const diffItems = buildDiffSummaryItems(change.diff_json as Parameters<typeof buildDiffSummaryItems>[0]);
  const compareColumns = buildEndpointCompareColumns(change);

  return (
    <div className="api-monitor-compare">
      <div className="api-monitor-compare__meta">
        <Tag color={CHANGE_TYPE_COLORS[change.change_type] || 'default'}>
          {CHANGE_TYPE_LABELS[change.change_type] || change.change_type}
        </Tag>
        <Typography.Text code>{change.endpoint_key}</Typography.Text>
        {change.source_file ? (
          <Typography.Text type="secondary">
            {change.source_file}
            {change.source_line ? `:${change.source_line}` : ''}
          </Typography.Text>
        ) : null}
      </div>

      <Typography.Paragraph className="api-monitor-compare__summary">{change.summary}</Typography.Paragraph>

      {diffItems.length > 0 ? (
        <div className="api-monitor-compare__diff-box">
          <Typography.Text strong className="api-monitor-compare__diff-title">
            变更摘要
          </Typography.Text>
          <ul className="api-monitor-compare__diff-list">
            {diffItems.map((item) => (
              <li key={item.text} className={DIFF_SUMMARY_CLASS[item.tone]}>
                {item.text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="api-monitor-compare__legend">
        <span className="api-monitor-compare__legend-item api-monitor-compare__legend-item--removed">
          红色：删除 / 改动前
        </span>
        <span className="api-monitor-compare__legend-item api-monitor-compare__legend-item--added">
          绿色：新增 / 改动后
        </span>
      </div>

      <div className="api-monitor-compare__panels">
        <SnapshotColumn
          title="改动前"
          tone="before"
          blocks={compareColumns.before}
          emptyText={compareColumns.beforeEmptyText}
        />
        <SnapshotColumn
          title="改动后"
          tone="after"
          blocks={compareColumns.after}
          emptyText={compareColumns.afterEmptyText}
        />
      </div>
    </div>
  );
}
