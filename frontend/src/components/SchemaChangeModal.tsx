import { List, Modal, Space, Tag, Typography } from 'antd';
import type { ActivityLog } from '../types';
import {
  getSchemaChanges,
  schemaOperationColor,
  schemaOperationLabel,
} from '../utils/schemaChangeLog';

interface Props {
  log: ActivityLog | null;
  open: boolean;
  onClose: () => void;
}

export default function SchemaChangeModal({ log, open, onClose }: Props) {
  const changes = log ? getSchemaChanges(log) : [];

  return (
    <Modal
      title={log ? `结构变更详情 · ${changes.length} 项` : '结构变更详情'}
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      {log?.summary ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 13 }}>
          {log.summary}
        </Typography.Paragraph>
      ) : null}

      <List
        size="small"
        dataSource={changes}
        locale={{ emptyText: '暂无变更明细' }}
        renderItem={(item) => (
          <List.Item style={{ display: 'block', paddingInline: 0 }}>
            <Space size={6} wrap style={{ marginBottom: item.details?.length ? 6 : 0 }}>
              <Tag color={schemaOperationColor(item.operation)}>
                {schemaOperationLabel(item.operation)}
              </Tag>
              {item.table ? (
                <Typography.Text code style={{ fontSize: 12 }}>
                  {item.table}
                </Typography.Text>
              ) : null}
            </Space>
            <Typography.Text style={{ display: 'block', fontSize: 13 }}>
              {item.summary}
            </Typography.Text>
            {item.details && item.details.length > 0 ? (
              <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: 'rgba(0,0,0,0.65)' }}>
                {item.details.map((detail) => (
                  <li key={`${item.table}-${detail}`} style={{ fontSize: 13, marginBottom: 2 }}>
                    {detail}
                  </li>
                ))}
              </ul>
            ) : null}
          </List.Item>
        )}
      />
    </Modal>
  );
}
