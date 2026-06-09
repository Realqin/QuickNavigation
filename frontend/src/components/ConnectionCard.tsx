import {
  DeleteOutlined,
  EditOutlined,
  HolderOutlined,
} from '@ant-design/icons';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button, Card, Popconfirm, Space, Tag, Typography } from 'antd';
import type { Connection } from '../types';
import { getTypeTextColor, hexWithAlpha, resolveTypeIcon } from '../utils/labelTheme';
import SubLinksPanel from './SubLinksPanel';

interface Props {
  connection: Connection;
  typeLabel?: string;
  typeColor?: string;
  typeIconIndex?: number;
  projectLabels?: string[];
  envLabels?: string[];
  editMode?: boolean;
  onEdit: (connection: Connection) => void;
  onDelete?: (connection: Connection) => void;
}

function TypeTag({ label, colorKey }: { label: string; colorKey: string }) {
  const fillColor = getTypeTextColor(colorKey);
  return (
    <Tag
      style={{
        color: 'rgba(0, 0, 0, 0.88)',
        border: 'none',
        backgroundColor: hexWithAlpha(fillColor, 0.18),
        marginInlineEnd: 0,
      }}
    >
      {label}
    </Tag>
  );
}

export default function ConnectionCard({
  connection,
  typeLabel,
  typeColor = 'blue',
  typeIconIndex = 0,
  projectLabels = [],
  envLabels = [],
  editMode = false,
  onEdit,
  onDelete,
}: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: connection.id,
    disabled: !editMode,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };

  const displayType = typeLabel ?? '连接';
  const TypeIcon = resolveTypeIcon(displayType, typeIconIndex);
  const typeFillColor = getTypeTextColor(typeColor);
  const headBackground = hexWithAlpha(typeFillColor, 0.18);

  const openMainUrl = () => {
    if (editMode) return;
    window.open(connection.url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <Card
        size="small"
        hoverable={!editMode}
        className={`connection-card${editMode ? ' connection-card--edit' : ''}`}
        styles={{
          header: {
            backgroundColor: headBackground,
            borderBottom: `1px solid ${hexWithAlpha(typeFillColor, 0.28)}`,
          },
        }}
        onClick={openMainUrl}
        title={
          <Space>
            {editMode && (
              <span
                {...listeners}
                className="drag-handle"
                onClick={(e) => e.stopPropagation()}
              >
                <HolderOutlined />
              </span>
            )}
            <TypeIcon style={{ color: 'rgba(0, 0, 0, 0.65)', fontSize: 16 }} />
            <span className="connection-card__name">{connection.name}</span>
          </Space>
        }
        extra={
          editMode ? (
            <Space size={4} onClick={(e) => e.stopPropagation()}>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEdit(connection)}
              />
              <Popconfirm
                title="确认删除该连接？"
                onConfirm={() => onDelete?.(connection)}
              >
                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>
          ) : null
        }
      >
        <div className="connection-card__content">
          <div className="connection-card__main">
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Typography.Text type="secondary" ellipsis>
                {connection.url}
              </Typography.Text>
              {connection.description && (
                <Typography.Text type="secondary" ellipsis>
                  {connection.description}
                </Typography.Text>
              )}
            </Space>
            <div onClick={(e) => e.stopPropagation()}>
              <SubLinksPanel subLinks={connection.sub_links} />
            </div>
          </div>
          <div className="connection-card__tags" onClick={(e) => e.stopPropagation()}>
            <TypeTag label={displayType} colorKey={typeColor} />
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
          </div>
        </div>
      </Card>
    </div>
  );
}
