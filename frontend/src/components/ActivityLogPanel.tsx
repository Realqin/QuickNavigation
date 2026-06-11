import { DatabaseOutlined, GithubOutlined } from '@ant-design/icons';
import { Badge, List, Space, Tag, Typography } from 'antd';
import type { ActivityLog } from '../types';
import { formatBeijingTime } from '../utils/dateTime';

interface Props {
  logs: ActivityLog[];
  onItemClick?: (log: ActivityLog) => void;
}

const sourceIcon: Record<string, React.ReactNode> = {
  github: <GithubOutlined style={{ color: '#a371f7' }} />,
  database: <DatabaseOutlined style={{ color: '#3fb950' }} />,
};

export default function ActivityLogPanel({ logs, onItemClick }: Props) {
  return (
    <div className="log-panel">
      <Typography.Title level={5} style={{ marginTop: 0 }}>
        实时动态
      </Typography.Title>
      <List
        size="small"
        dataSource={logs}
        locale={{ emptyText: '暂无动态' }}
        renderItem={(item) => (
          <List.Item
            className={`log-item ${item.is_read ? 'read' : 'unread'}`}
            onClick={() => onItemClick?.(item)}
          >
            <List.Item.Meta
              avatar={
                <Badge dot={!item.is_read}>
                  {sourceIcon[item.source_type] ?? <GithubOutlined />}
                </Badge>
              }
              title={
                <Space wrap size={4}>
                  <Typography.Text strong ellipsis style={{ maxWidth: 220 }}>
                    {item.title}
                  </Typography.Text>
                  <Tag>{item.source_type}</Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={2}>
                  {item.summary && (
                    <Typography.Text type="secondary" ellipsis>
                      {item.summary}
                    </Typography.Text>
                  )}
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {item.author ? `${item.author} · ` : ''}
                    {formatBeijingTime(item.occurred_at)}
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
}
