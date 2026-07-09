import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { App, Button, Input, Select, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useState } from 'react';
import { fetchOperationLogs } from '../api';
import type { OperationLogItem } from '../types/auth';
import { showApiError } from '../utils/apiError';
import { formatBeijingTime } from '../utils/dateTime';

const ACTION_OPTIONS = [
  { value: '', label: '全部操作' },
  { value: 'create', label: '新增' },
  { value: 'update', label: '编辑' },
  { value: 'delete', label: '删除' },
  { value: 'login', label: '登录' },
  { value: 'logout', label: '退出' },
  { value: 'open', label: '打开' },
];

export default function OperationLogPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<OperationLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [username, setUsername] = useState('');
  const [action, setAction] = useState('');

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchOperationLogs({
        keyword: keyword.trim() || undefined,
        username: username.trim() || undefined,
        action: action || undefined,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (error) {
      showApiError(error, '加载操作日志失败');
    } finally {
      setLoading(false);
    }
  }, [action, keyword, username]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const columns: ColumnsType<OperationLogItem> = [
    {
      title: '操作人',
      dataIndex: 'username',
      width: 120,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatBeijingTime(value) || '-',
    },
    {
      title: '操作',
      dataIndex: 'action_label',
      width: 90,
    },
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
    },
    {
      title: 'IP',
      dataIndex: 'ip_address',
      width: 140,
      render: (value?: string | null) => value || '-',
    },
  ];

  return (
    <div className="page-panel">
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          placeholder="搜索内容"
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => void loadItems()}
          style={{ width: 220 }}
        />
        <Input
          allowClear
          placeholder="操作人"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onPressEnter={() => void loadItems()}
          style={{ width: 160 }}
        />
        <Select
          value={action}
          options={ACTION_OPTIONS}
          onChange={setAction}
          style={{ width: 140 }}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => void loadItems()}>
          搜索
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void loadItems()}>
          刷新
        </Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={{ total, showSizeChanger: false, pageSize: 200 }}
        scroll={{ x: 900 }}
      />
    </div>
  );
}
