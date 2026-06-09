import { LinkOutlined } from '@ant-design/icons';
import { Collapse, List, Typography } from 'antd';
import type { SubLink } from '../types';

interface Props {
  subLinks?: SubLink[];
  compact?: boolean;
}

export default function SubLinksPanel({ subLinks, compact = false }: Props) {
  if (!subLinks?.length) {
    return null;
  }

  const list = (
    <List
      size="small"
      dataSource={subLinks}
      renderItem={(item) => (
        <List.Item className="sub-link-item">
          <Typography.Link
            href={item.url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
          >
            <LinkOutlined style={{ marginRight: 6 }} />
            {item.name}
          </Typography.Link>
          {!compact && (
            <Typography.Text type="secondary" ellipsis style={{ marginLeft: 8, flex: 1 }}>
              {item.url}
            </Typography.Text>
          )}
        </List.Item>
      )}
    />
  );

  if (compact) {
    return list;
  }

  return (
    <Collapse
      size="small"
      className="sub-links-collapse"
      onClick={(e) => e.stopPropagation()}
      items={[
        {
          key: 'sub-links',
          label: `子链接 (${subLinks.length})`,
          children: list,
        },
      ]}
    />
  );
}
