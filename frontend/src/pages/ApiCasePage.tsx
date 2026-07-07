import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, UndoOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  batchDeleteApiTestCases,
  createApiTestCase,
  deleteApiTestCase,
  fetchApiTestCases,
  permanentDeleteApiTestCase,
  restoreApiTestCase,
  updateApiTestCase,
} from '../api';
import ApiCaseFormModal from '../components/ApiCaseFormModal';
import { useDictGroup } from '../hooks/useDict';
import { formatCaseHeadersDisplay, formatCaseRequestParamsDisplay } from '../utils/caseRequestParts';
import { renderCaseExecuteStatusCell } from '../utils/caseExecuteStatus';
import { showApiError } from '../utils/apiError';
import { formatExpectedResponseDisplay } from '../utils/responseAssert';
import type { ApiTestCase, ApiTestCaseFormValues } from '../types/apiTestCase';
import {
  API_TEST_CASE_STATUS_OPTIONS,
  API_TEST_CASE_TYPE_LABELS,
} from '../types/apiTestCase';

const TABLE_SCROLL_Y = 'calc(100vh - 360px)';
const PAGE_SIZE_OPTIONS = [8, 10, 15, 30, 50, 100];

interface FilterValues {
  project_id?: number;
  environment_id?: number;
  service?: string;
  keyword?: string;
  status: string;
}

function ellipsisCell(value?: string | null, width = 180) {
  if (!value) {
    return '-';
  }
  return (
    <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: width }}>
      {value}
    </Typography.Text>
  );
}

export default function ApiCasePage() {
  const { projects, environments } = useDictGroup();
  const [form] = Form.useForm<FilterValues>();

  const [data, setData] = useState<ApiTestCase[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [filters, setFilters] = useState<FilterValues>({ status: 'active' });
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ApiTestCase | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchApiTestCases({
        project_id: filters.project_id,
        environment_id: filters.environment_id,
        service: filters.service?.trim() || undefined,
        keyword: filters.keyword?.trim() || undefined,
        status: filters.status || 'active',
        page,
        page_size: pageSize,
      });
      setData(result.items);
      setTotal(result.total);
      setSelectedRowKeys((prev) =>
        prev.filter((id) => result.items.some((item) => item.id === id)),
      );
    } catch (error) {
      showApiError(error, '加载用例列表失败');
    } finally {
      setLoading(false);
    }
  }, [filters, page, pageSize]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((record: ApiTestCase) => {
    setEditing(record);
    setModalOpen(true);
  }, []);

  const handleSubmit = async (values: ApiTestCaseFormValues) => {
    try {
      if (editing) {
        await updateApiTestCase(editing.id, values);
        message.success('更新成功');
      } else {
        await createApiTestCase(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      await loadData();
    } catch (error) {
      showApiError(error, '保存失败');
      throw new Error('save failed');
    }
  };

  const handleDelete = useCallback(async (id: number) => {
    try {
      await deleteApiTestCase(id);
      message.success('已移入已删除');
      await loadData();
    } catch (error) {
      showApiError(error, '删除失败');
    }
  }, [loadData]);

  const handleRestore = useCallback(async (id: number) => {
    try {
      await restoreApiTestCase(id);
      message.success('已恢复');
      await loadData();
    } catch (error) {
      showApiError(error, '恢复失败');
    }
  }, [loadData]);

  const handlePermanentDelete = useCallback(async (id: number) => {
    try {
      await permanentDeleteApiTestCase(id);
      message.success('已永久删除');
      setSelectedRowKeys((prev) => prev.filter((itemId) => itemId !== id));
      await loadData();
    } catch (error) {
      showApiError(error, '永久删除失败');
    }
  }, [loadData]);

  const handleBatchDelete = useCallback(async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选要删除的用例');
      return;
    }
    setBatchDeleting(true);
    try {
      const result = await batchDeleteApiTestCases(selectedRowKeys);
      const parts: string[] = [];
      if (result.soft_deleted > 0) {
        parts.push(`移入已删除 ${result.soft_deleted} 条`);
      }
      if (result.hard_deleted > 0) {
        parts.push(`永久删除 ${result.hard_deleted} 条`);
      }
      if (result.not_found > 0) {
        parts.push(`${result.not_found} 条不存在`);
      }
      message.success(parts.length ? parts.join('，') : '操作完成');
      setSelectedRowKeys([]);
      await loadData();
    } catch (error) {
      showApiError(error, '批量删除失败');
    } finally {
      setBatchDeleting(false);
    }
  }, [loadData, selectedRowKeys]);

  const applyFilters = () => {
    setPage(1);
    setSelectedRowKeys([]);
    setFilters(form.getFieldsValue());
  };

  const selectedRows = useMemo(
    () => data.filter((item) => selectedRowKeys.includes(item.id)),
    [data, selectedRowKeys],
  );

  const batchDeleteHint = useMemo(() => {
    const activeCount = selectedRows.filter((item) => item.status !== 'deleted').length;
    const deletedCount = selectedRows.length - activeCount;
    if (deletedCount === 0) {
      return `确认删除选中的 ${selectedRows.length} 条用例？将移入已删除。`;
    }
    if (activeCount === 0) {
      return `确认永久删除选中的 ${selectedRows.length} 条已删除用例？此操作不可恢复。`;
    }
    return `确认删除选中的 ${selectedRows.length} 条用例？其中 ${activeCount} 条移入已删除，${deletedCount} 条永久删除。`;
  }, [selectedRows]);

  const columns = useMemo<ColumnsType<ApiTestCase>>(
    () => [
      {
        title: '序号',
        width: 70,
        fixed: 'left',
        render: (_value, _record, index) => (page - 1) * pageSize + index + 1,
      },
      {
        title: '项目',
        dataIndex: 'project_display',
        width: 120,
        render: (value) => ellipsisCell(value, 100),
      },
      {
        title: '环境',
        dataIndex: 'environment_display',
        width: 100,
        render: (value) => ellipsisCell(value, 80),
      },
      {
        title: '服务',
        dataIndex: 'service',
        width: 130,
        render: (value) => ellipsisCell(value, 110),
      },
      {
        title: '用例名称',
        dataIndex: 'name',
        width: 180,
        render: (value) => ellipsisCell(value, 160),
      },
      {
        title: '接口地址',
        dataIndex: 'api_path',
        width: 260,
        render: (value) => (
          <Typography.Text code ellipsis={{ tooltip: value }} style={{ maxWidth: 240 }}>
            {value}
          </Typography.Text>
        ),
      },
      {
        title: '请求方式',
        dataIndex: 'method',
        width: 90,
        render: (value) => <Tag>{value}</Tag>,
      },
      {
        title: '请求头',
        dataIndex: 'request_headers',
        width: 160,
        render: (_value, record) =>
          ellipsisCell(formatCaseHeadersDisplay(record.request_headers, record.request_params), 140),
      },
      {
        title: '请求参数',
        dataIndex: 'request_body',
        width: 160,
        render: (_value, record) =>
          ellipsisCell(formatCaseRequestParamsDisplay(record.request_params, record.request_body), 140),
      },
      {
        title: '预期响应码',
        dataIndex: 'expected_status',
        width: 110,
      },
      {
        title: '预期响应结果',
        dataIndex: 'expected_response',
        width: 180,
        render: (_value, record) =>
          ellipsisCell(
            formatExpectedResponseDisplay(
              record.response_assert_mode,
              record.expected_response,
              record.response_assert_rules,
            ),
            160,
          ),
      },
      {
        title: '执行状态',
        key: 'last_exec',
        width: 100,
        align: 'center',
        render: (_value, record) => renderCaseExecuteStatusCell(record),
      },
      {
        title: '用例类型',
        dataIndex: 'case_type',
        width: 100,
        render: (value: string) => API_TEST_CASE_TYPE_LABELS[value] || value,
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 90,
        render: (value: string) =>
          value === 'deleted' ? <Tag color="red">已删除</Tag> : <Tag color="green">正常</Tag>,
      },
      {
        title: '操作',
        key: 'actions',
        width: 168,
        fixed: 'right',
        render: (_, record) => (
          <Space size={4}>
            {record.status === 'deleted' ? (
              <>
                <Button
                  type="text"
                  size="small"
                  icon={<UndoOutlined />}
                  title="恢复"
                  onClick={() => handleRestore(record.id)}
                />
                <Popconfirm
                  title="确认永久删除该用例？"
                  description="永久删除后无法恢复"
                  onConfirm={() => handlePermanentDelete(record.id)}
                >
                  <Button type="text" size="small" danger title="永久删除">
                    永久删除
                  </Button>
                </Popconfirm>
              </>
            ) : (
              <>
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  title="编辑"
                  onClick={() => openEdit(record)}
                />
                <Popconfirm title="确认删除该用例？" onConfirm={() => handleDelete(record.id)}>
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} title="删除" />
                </Popconfirm>
              </>
            )}
          </Space>
        ),
      },
    ],
    [page, pageSize, handleDelete, handlePermanentDelete, handleRestore, openEdit],
  );

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: (string | number)[]) => {
      setSelectedRowKeys(keys.map((key) => Number(key)));
    },
  };

  return (
    <div className="tab-page api-case-page">
      <div className="tab-page-toolbar">
        <Typography.Title level={5} style={{ margin: 0 }}>
          接口用例管理
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()} loading={loading}>
            刷新
          </Button>
          <Popconfirm
            title="批量删除"
            description={batchDeleteHint}
            disabled={selectedRowKeys.length === 0}
            onConfirm={() => handleBatchDelete()}
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={selectedRowKeys.length === 0}
              loading={batchDeleting}
            >
              批量删除{selectedRowKeys.length > 0 ? ` (${selectedRowKeys.length})` : ''}
            </Button>
          </Popconfirm>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增
          </Button>
        </Space>
      </div>

      <Form
        form={form}
        layout="inline"
        className="api-case-page__filters"
        initialValues={{ status: 'active' }}
      >
        <Form.Item name="project_id" label="项目">
          <Select allowClear style={{ width: 140 }} placeholder="全部" options={projects.options} />
        </Form.Item>
        <Form.Item name="environment_id" label="环境">
          <Select allowClear style={{ width: 120 }} placeholder="全部" options={environments.options} />
        </Form.Item>
        <Form.Item name="service" label="服务">
          <Input allowClear placeholder="服务名" style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="keyword" label="关键词">
          <Input allowClear placeholder="名称/地址" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item name="status" label="状态">
          <Select style={{ width: 120 }} options={API_TEST_CASE_STATUS_OPTIONS} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" onClick={applyFilters}>
            查询
          </Button>
        </Form.Item>
      </Form>

      <Table
        className="api-case-page__table"
        rowKey="id"
        loading={loading}
        rowSelection={rowSelection}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: 2248, y: TABLE_SCROLL_Y }}
      />

      <div className="api-case-page__pagination">
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          showTotal={(count) => `共 ${count} 条`}
          onChange={(nextPage, nextPageSize) => {
            setPage(nextPage);
            if (nextPageSize && nextPageSize !== pageSize) {
              setPageSize(nextPageSize);
              setPage(1);
            }
          }}
        />
      </div>

      <ApiCaseFormModal
        open={modalOpen}
        editing={editing}
        projectOptions={projects.options}
        environmentOptions={environments.options}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
