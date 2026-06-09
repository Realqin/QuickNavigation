import {
  DatabaseOutlined,
  EditOutlined,
  GithubOutlined,
  GlobalOutlined,
  HolderOutlined,
} from '@ant-design/icons';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, Space, Tag, Tooltip, Typography } from 'antd';
import type { Connection } from '../types';
import SubLinksPanel from './SubLinksPanel';

function getTypeIcon(typeName?: string) {
  const key = (typeName ?? '').toLowerCase();
  if (key.includes('github')) return <GithubOutlined />;
  if (key.includes('数据库') || key.includes('database')) return <DatabaseOutlined />;
  return <GlobalOutlined />;
}

function getTypeColor(typeName?: string) {
  const key = (typeName ?? '').toLowerCase();
  if (key.includes('github')) return 'purple';
  if (key.includes('数据库') || key.includes('database')) return 'green';
  return 'blue';
}

interface Props {
  connection: Connection;
  typeLabel?: string;
  projectLabels?: string[];
  envLabels?: string[];
  onEdit: (connection: Connection) => void;
}

export default function ConnectionCard({
  connection,
  typeLabel,
  projectLabels = [],
  envLabels = [],
  onEdit,
}: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: connection.id,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };

  const displayType = typeLabel ?? '连接';
  const openMainUrl = () => window.open(connection.url, '_blank', 'noopener,noreferrer');

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <Card
        size="small"
        hoverable
        className="connection-card"
        onClick={openMainUrl}
        title={
          <Space>
            <span
              {...listeners}
              className="drag-handle"
              onClick={(e) => e.stopPropagation()}
            >
              <HolderOutlined />
            </span>
            {getTypeIcon(displayType)}
            <span>{connection.name}</span>
          </Space>
        }
        extra={
          <Tooltip title="编辑">
            <EditOutlined
              onClick={(e) => {
                e.stopPropagation();
                onEdit(connection);
              }}
            />
          </Tooltip>
        }
      >
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Typography.Text type="secondary" ellipsis>
            {connection.url}
          </Typography.Text>
          {connection.description && (
            <Typography.Text type="secondary" ellipsis>
              {connection.description}
            </Typography.Text>
          )}
          <Space wrap>
            <Tag color={getTypeColor(displayType)}>{displayType}</Tag>
            {!connection.is_shared && (
              <>
                {projectLabels.map((item) => (
                  <Tag key={`p-${item}`}>{item}</Tag>
                ))}
                {envLabels.map((item) => (
                  <Tag key={`e-${item}`} color="orange">
                    {item}
                  </Tag>
                ))}
              </>
            )}
          </Space>
          <div onClick={(e) => e.stopPropagation()}>
            <SubLinksPanel subLinks={connection.sub_links} />
          </div>
        </Space>
      </Card>
    </div>
  );
}
