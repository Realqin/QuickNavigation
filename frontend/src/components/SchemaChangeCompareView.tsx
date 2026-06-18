import { Tag, Typography } from 'antd';
import type { SchemaChangeItem } from '../utils/schemaChangeLog';
import {
  resolveSchemaChangeCompare,
  schemaOperationColor,
  schemaOperationLabel,
} from '../utils/schemaChangeLog';

interface Props {
  item: SchemaChangeItem;
}

function SchemaPanel({
  title,
  tone,
  text,
}: {
  title: string;
  tone: 'before' | 'after';
  text: string;
}) {
  return (
    <div className={`api-monitor-compare__column api-monitor-compare__column--${tone}`}>
      <div className={`api-monitor-compare__column-head api-monitor-compare__column-head--${tone}`}>
        {title}
      </div>
      <pre className="schema-change-compare__pre">{text}</pre>
    </div>
  );
}

export default function SchemaChangeCompareView({ item }: Props) {
  const compare = resolveSchemaChangeCompare(item);

  return (
    <div className="schema-change-compare api-monitor-compare">
      <div className="api-monitor-compare__meta">
        <Tag color={schemaOperationColor(item.operation)}>
          {schemaOperationLabel(item.operation)}
        </Tag>
        {item.table ? (
          <Typography.Text code style={{ fontSize: 12 }}>
            {item.table}
          </Typography.Text>
        ) : null}
      </div>

      <Typography.Paragraph className="api-monitor-compare__summary">{item.summary}</Typography.Paragraph>

      {compare.diff.length > 0 ? (
        <div className="api-monitor-compare__diff-box">
          <Typography.Text strong className="api-monitor-compare__diff-title">
            区别点
          </Typography.Text>
          <ul className="api-monitor-compare__diff-list">
            {compare.diff.map((detail) => (
              <li key={`${item.table}-${detail}`} className="api-monitor-compare__diff-item--modified">
                {detail}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="api-monitor-compare__legend">
        <span className="api-monitor-compare__legend-item api-monitor-compare__legend-item--removed">
          修改前
        </span>
        <span className="api-monitor-compare__legend-item api-monitor-compare__legend-item--added">
          修改后
        </span>
      </div>

      <div className="api-monitor-compare__panels">
        <SchemaPanel title="修改前" tone="before" text={compare.before} />
        <SchemaPanel title="修改后" tone="after" text={compare.after} />
      </div>
    </div>
  );
}
