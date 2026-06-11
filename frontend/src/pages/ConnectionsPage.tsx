import {
  CaretDownOutlined,
  CaretRightOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  Badge,
  Button,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  batchDeleteConnections,
  createConnection,
  deleteConnection,
  fetchConnections,
  FILTER_EMPTY,
  pingConnection,
  updateConnection,
} from '../api';
import ConnectionFormModal from '../components/ConnectionFormModal';
import { useDictGroup } from '../hooks/useDict';
import type { Connection, ConnectionFormValues, SubLink } from '../types';

interface FilterValues {
  name?: string;
  project?: number;
  environment?: number;
  group_id?: number;
}

type RowKind = 'parent' | 'child';

interface ConnectionRow {
  rowKey: string;
  kind: RowKind;
  connection: Connection;
  subIndex?: number;
  subLink?: SubLink;
}

const PING_REFRESH_MS = 3 * 60 * 1000;
const CHILD_NAME_INDENT = 32;

function renderTags(ids: number[] | undefined, idMap: Record<number, string>, color?: string) {
  if (!ids?.length) return '-';
  return (
    <Space wrap size={[4, 4]}>
      {ids.map((item) => (
        <Tag key={item} color={color}>
          {idMap[item] ?? item}
        </Tag>
      ))}
    </Space>
  );
}

function renderReachabilityStatus(reachable: boolean | null | undefined) {
  if (reachable == null) {
    return <Badge status="default" text="未检测" />;
  }
  if (reachable) {
    return <Badge status="success" text="正常" />;
  }
  return <Badge status="error" text="无法连通" />;
}

function buildRows(connections: Connection[], expandedIds: Set<number>): ConnectionRow[] {
  const rows: ConnectionRow[] = [];
  for (const connection of connections) {
    rows.push({
      rowKey: `p-${connection.id}`,
      kind: 'parent',
      connection,
    });
    const subLinks = connection.sub_links ?? [];
    if (subLinks.length > 0 && expandedIds.has(connection.id)) {
      subLinks.forEach((subLink, subIndex) => {
        rows.push({
          rowKey: `c-${connection.id}-${subIndex}`,
          kind: 'child',
          connection,
          subIndex,
          subLink,
        });
      });
    }
  }
  return rows;
}

export default function ConnectionsPage() {
  const { projects, environments, labels, connectionGroups } = useDictGroup();
  const [form] = Form.useForm<FilterValues>();
  const projectFilterOptions = useMemo(
    () => [{ label: '其他', value: FILTER_EMPTY }, ...projects.options],
    [projects.options],
  );
  const environmentFilterOptions = useMemo(
    () => [{ label: '其他', value: FILTER_EMPTY }, ...environments.options],
    [environments.options],
  );
  const [data, setData] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [pingingKeys, setPingingKeys] = useState<string[]>([]);
  const nameDebounceRef = useRef<number | null>(null);

  const tableRows = useMemo(() => buildRows(data, expandedIds), [data, expandedIds]);

  const loadData = useCallback(async (filters?: FilterValues, silent = false) => {
    const values = filters ?? form.getFieldsValue();
    if (!silent) {
      setLoading(true);
    }
    try {
      const list = await fetchConnections({
        name: values.name || undefined,
        project: values.project,
        environment: values.environment,
        group_id: values.group_id,
      });
      setData(list);
      setSelectedRowKeys((prev) => prev.filter((id) => list.some((item) => item.id === id)));
      setExpandedIds((prev) => {
        const next = new Set<number>();
        prev.forEach((id) => {
          if (list.some((item) => item.id === id)) {
            next.add(id);
          }
        });
        return next;
      });
    } catch {
      if (!silent) {
        message.error('加载失败');
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [form]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadData(undefined, true);
    }, PING_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadData]);

  useEffect(() => {
    return () => {
      if (nameDebounceRef.current) {
        window.clearTimeout(nameDebounceRef.current);
      }
    };
  }, []);

  const toggleExpand = (connectionId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(connectionId)) {
        next.delete(connectionId);
      } else {
        next.add(connectionId);
      }
      return next;
    });
  };

  const handleValuesChange = (changed: Partial<FilterValues>, allValues: FilterValues) => {
    if ('project' in changed || 'environment' in changed || 'group_id' in changed) {
      loadData(allValues);
      return;
    }
    if ('name' in changed) {
      if (nameDebounceRef.current) {
        window.clearTimeout(nameDebounceRef.current);
      }
      nameDebounceRef.current = window.setTimeout(() => {
        loadData(allValues);
      }, 400);
    }
  };

  const handleSubmit = async (values: ConnectionFormValues) => {
    try {
      if (editing) {
        await updateConnection(editing.id, values);
        message.success('更新成功');
      } else {
        await createConnection(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      loadData();
    } catch {
      message.error('保存失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteConnection(id);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleBatchDelete = async () => {
    if (!selectedRowKeys.length) return;
    try {
      await batchDeleteConnections(selectedRowKeys);
      message.success(`已删除 ${selectedRowKeys.length} 条连接`);
      setSelectedRowKeys([]);
      loadData();
    } catch {
      message.error('批量删除失败');
    }
  };

  const handlePing = async (row: ConnectionRow) => {
    const { connection, subIndex } = row;
    const pingKey = subIndex === undefined ? `p-${connection.id}` : `c-${connection.id}-${subIndex}`;
    setPingingKeys((prev) => [...prev, pingKey]);
    try {
      const result = await pingConnection(connection.id, subIndex);
      setData((prev) =>
        prev.map((item) => (item.id === connection.id ? result : item)),
      );
      const reachable =
        subIndex === undefined
          ? result.is_reachable
          : result.sub_links?.[subIndex]?.is_reachable;
      message.success(reachable ? '连接正常' : '无法连通');
    } catch {
      message.error('测试连接失败');
    } finally {
      setPingingKeys((prev) => prev.filter((key) => key !== pingKey));
    }
  };

  return (
    <div className="tab-page">
      <div className="tab-page-toolbar">
        <Typography.Title level={5} style={{ margin: 0 }}>
          连接管理
        </Typography.Title>
        <Space>
          <Popconfirm
            title={`确认删除选中的 ${selectedRowKeys.length} 条连接？`}
            onConfirm={handleBatchDelete}
            disabled={!selectedRowKeys.length}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!selectedRowKeys.length}>
              批量删除{selectedRowKeys.length ? ` (${selectedRowKeys.length})` : ''}
            </Button>
          </Popconfirm>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
            disabled={!labels.options.length}
          >
            新增
          </Button>
        </Space>
      </div>

      <Form
        form={form}
        layout="inline"
        style={{ marginBottom: 16 }}
        onValuesChange={handleValuesChange}
      >
        <Form.Item name="name" label="名称">
          <Input placeholder="模糊搜索" allowClear />
        </Form.Item>
        <Form.Item name="project" label="项目">
          <Select
            allowClear
            style={{ width: 160 }}
            placeholder="项目"
            options={projectFilterOptions}
          />
        </Form.Item>
        <Form.Item name="environment" label="环境">
          <Select
            allowClear
            style={{ width: 140 }}
            placeholder="环境"
            options={environmentFilterOptions}
          />
        </Form.Item>
        <Form.Item name="group_id" label="分组">
          <Select
            allowClear
            style={{ width: 140 }}
            placeholder="全部"
            options={connectionGroups.options}
          />
        </Form.Item>
      </Form>

      <Table
        rowKey="rowKey"
        loading={loading}
        dataSource={tableRows}
        pagination={{ pageSize: 10 }}
        rowSelection={{
          selectedRowKeys: selectedRowKeys.map((id) => `p-${id}`),
          onChange: (keys) => {
            const ids = (keys as string[])
              .filter((key) => key.startsWith('p-'))
              .map((key) => Number(key.slice(2)));
            setSelectedRowKeys(ids);
          },
          getCheckboxProps: (row: ConnectionRow) => ({
            disabled: row.kind === 'child',
            style: row.kind === 'child' ? { visibility: 'hidden' } : undefined,
          }),
        }}
        columns={[
          {
            title: '名称',
            dataIndex: 'name',
            render: (_, row) => {
              const { connection, kind, subLink } = row;
              const subCount = connection.sub_links?.length ?? 0;
              const expanded = expandedIds.has(connection.id);

              if (kind === 'child' && subLink) {
                return (
                  <span style={{ paddingLeft: CHILD_NAME_INDENT, display: 'inline-block' }}>
                    {subLink.name}
                  </span>
                );
              }

              return (
                <Space size={4}>
                  {subCount > 0 ? (
                    <Button
                      type="text"
                      size="small"
                      icon={expanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
                      onClick={() => toggleExpand(connection.id)}
                      style={{ width: 24, padding: 0 }}
                    />
                  ) : (
                    <span style={{ display: 'inline-block', width: 24 }} />
                  )}
                  <span>{connection.name}</span>
                  {subCount > 0 && <Tag color="blue">{subCount} 个子链接</Tag>}
                </Space>
              );
            },
          },
          {
            title: 'URL',
            dataIndex: 'url',
            ellipsis: true,
            render: (_, row) => {
              const url = row.kind === 'child' ? row.subLink?.url : row.connection.url;
              if (!url) return '-';
              return (
                <a href={url} target="_blank" rel="noreferrer">
                  {url}
                </a>
              );
            },
          },
          {
            title: '状态',
            dataIndex: 'is_reachable',
            width: 120,
            render: (_, row) => {
              const reachable =
                row.kind === 'child'
                  ? row.subLink?.is_reachable
                  : row.connection.is_reachable;
              const checkedAt =
                row.kind === 'child'
                  ? row.subLink?.last_checked_at
                  : row.connection.last_checked_at;
              return (
                <Tooltip
                  title={
                    checkedAt
                      ? `最近检测：${new Date(checkedAt).toLocaleString()}`
                      : '尚未检测'
                  }
                >
                  {renderReachabilityStatus(reachable)}
                </Tooltip>
              );
            },
          },
          {
            title: '项目',
            dataIndex: 'projects',
            render: (_, row) => renderTags(row.connection.projects, projects.idMap),
          },
          {
            title: '环境',
            dataIndex: 'environments',
            render: (_, row) => renderTags(row.connection.environments, environments.idMap, 'orange'),
          },
          {
            title: '类型',
            dataIndex: 'type',
            render: (_, row) => (
              <Tag>{labels.idMap[row.connection.type] ?? row.connection.type}</Tag>
            ),
          },
          {
            title: '分组',
            dataIndex: 'group_id',
            render: (_, row) =>
              connectionGroups.idMap[row.connection.group_id ?? 0] ?? '-',
          },
          {
            title: '操作',
            width: 220,
            render: (_, row) => {
              const pingKey =
                row.subIndex === undefined
                  ? `p-${row.connection.id}`
                  : `c-${row.connection.id}-${row.subIndex}`;

              if (row.kind === 'child') {
                return (
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={pingingKeys.includes(pingKey)}
                    onClick={() => handlePing(row)}
                  >
                    测试连接
                  </Button>
                );
              }

              return (
                <Space>
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={pingingKeys.includes(pingKey)}
                    onClick={() => handlePing(row)}
                  >
                    测试连接
                  </Button>
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => {
                      setEditing(row.connection);
                      setModalOpen(true);
                    }}
                  />
                  <Popconfirm title="确认删除？" onConfirm={() => handleDelete(row.connection.id)}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              );
            },
          },
        ]}
      />

      <ConnectionFormModal
        open={modalOpen}
        connection={editing}
        projectOptions={projects.options}
        environmentOptions={environments.options}
        labelOptions={labels.options}
        groupOptions={connectionGroups.options}
        groupItems={connectionGroups.items}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
