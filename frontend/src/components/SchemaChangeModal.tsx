import { Divider, Modal, Typography } from 'antd';
import type { ActivityLog } from '../types';
import { getSchemaChanges } from '../utils/schemaChangeLog';
import SchemaChangeCompareView from './SchemaChangeCompareView';

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
      width={1080}
      destroyOnHidden
      className="schema-change-modal"
    >
      {log?.summary ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 13 }}>
          {log.summary}
        </Typography.Paragraph>
      ) : null}

      {changes.length === 0 ? (
        <Typography.Text type="secondary">暂无变更明细</Typography.Text>
      ) : (
        changes.map((item, index) => (
          <div key={`${item.operation}-${item.table ?? index}`}>
            {index > 0 ? <Divider style={{ margin: '16px 0' }} /> : null}
            <SchemaChangeCompareView item={item} />
          </div>
        ))
      )}
    </Modal>
  );
}
