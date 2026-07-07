import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { App, Button, Modal, Popconfirm, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createApiTestCase,
  deleteApiTestCase,
  fetchApiMonitorProxy,
  generateApiTestCasesFromEndpoint,
  fetchApiTestCases,
  saveApiTestCaseExecutionResult,
  updateApiTestCase,
} from '../../api';
import ApiCaseFormModal from '../../components/ApiCaseFormModal';
import type { ApiMonitorEndpoint } from '../../types/apiMonitor';
import type { ApiTestCase, ApiTestCaseFormValues } from '../../types/apiTestCase';
import type { ApiMonitorEnvPreset } from './apiMonitorEnvPreset';
import { buildDebugHeadersFromPreset } from './apiMonitorEnvPreset';
import { buildCaseDefaultsFromEndpoint, parseCaseRequestParams } from './buildCaseFromEndpoint';
import { resolveCaseHeaders } from '../../utils/caseRequestParts';
import { evaluateResponseAssert, formatExpectedResponseDisplay } from '../../utils/responseAssert';
import {
  formatProxyResponseBody,
  renderCaseExecuteStatusCell,
} from '../../utils/caseExecuteStatus';
import { getApiErrorMessage, showApiError } from '../../utils/apiError';
import { buildDebugUrl } from './debugUtils';

interface ApiMonitorEndpointCasesPanelProps {
  endpoint: ApiMonitorEndpoint;
  projectId?: number;
  environmentId?: number;
  service?: string | null;
  envPreset: ApiMonitorEnvPreset;
  projectOptions: Array<{ value: number; label: string }>;
  environmentOptions: Array<{ value: number; label: string }>;
}

function ellipsisCell(value?: string | null, width = 160) {
  if (!value) {
    return '-';
  }
  return (
    <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: width }}>
      {value}
    </Typography.Text>
  );
}

export default function ApiMonitorEndpointCasesPanel({
  endpoint,
  projectId,
  environmentId,
  service,
  envPreset,
  projectOptions,
  environmentOptions,
}: ApiMonitorEndpointCasesPanelProps) {
  const { message: appMessage } = App.useApp();
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [cases, setCases] = useState<ApiTestCase[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ApiTestCase | null>(null);
  const [executingId, setExecutingId] = useState<number | null>(null);
  const [executeResult, setExecuteResult] = useState<{
    caseName: string;
    pass: boolean;
    statusCode: number;
    body: string;
    detail: string;
  } | null>(null);

  const contextReady = Boolean(projectId && environmentId && service);

  const caseDefaults = useMemo(() => {
    if (!contextReady || projectId == null || environmentId == null || !service) {
      return null;
    }
    return buildCaseDefaultsFromEndpoint(endpoint, {
      project_id: projectId,
      environment_id: environmentId,
      service,
    });
  }, [contextReady, endpoint, projectId, environmentId, service]);

  const loadCases = useCallback(async () => {
    if (!endpoint.id) {
      setCases([]);
      return;
    }
    setLoading(true);
    try {
      const result = await fetchApiTestCases({
        endpoint_id: endpoint.id,
        status: 'active',
        page: 1,
        page_size: 200,
      });
      setCases(result.items);
    } catch (error) {
      showApiError(error, '加载关联用例失败');
    } finally {
      setLoading(false);
    }
  }, [appMessage, endpoint.id]);

  useEffect(() => {
    setVisible(false);
    setCases([]);
    setEditing(null);
    setModalOpen(false);
    setExecuteResult(null);
  }, [endpoint.id]);

  useEffect(() => {
    if (visible) {
      loadCases();
    }
  }, [visible, loadCases]);

  const handleGenerate = async () => {
    if (!contextReady || projectId == null || environmentId == null || !service) {
      appMessage.warning('请先选择项目、环境和服务');
      return;
    }
    setGenerating(true);
    try {
      const result = await generateApiTestCasesFromEndpoint({
        endpoint_id: endpoint.id,
        project_id: projectId,
        environment_id: environmentId,
        service,
        method: endpoint.method,
        api_path: endpoint.path,
        summary: endpoint.summary,
        parameters: endpoint.parameters,
      });
      setCases(result.items);
      setVisible(true);
      appMessage.success(result.created > 0 ? '已生成默认冒烟用例' : '已加载关联用例');
    } catch (error) {
      showApiError(error, '用例生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((record: ApiTestCase) => {
    setEditing(record);
    setModalOpen(true);
  }, []);

  const handleDelete = useCallback(async (id: number) => {
    try {
      await deleteApiTestCase(id);
      appMessage.success('删除成功');
      await loadCases();
    } catch (error) {
      showApiError(error, '删除失败');
    }
  }, [appMessage, loadCases]);

  const patchCaseInList = useCallback((updated: ApiTestCase) => {
    setCases((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
  }, []);

  const handleExecute = useCallback(async (record: ApiTestCase) => {
    if (!envPreset.serverAddress.trim()) {
      appMessage.warning('请先在环境预置中配置服务器地址');
      return;
    }
    setExecutingId(record.id);
    try {
      const { query, path } = parseCaseRequestParams(record.request_params);
      const url = buildDebugUrl(envPreset.serverAddress, '', record.api_path, path, query);
      const presetHeaders = buildDebugHeadersFromPreset(envPreset);
      const caseHeaders = resolveCaseHeaders(record.request_headers, record.request_params);
      const headers = { ...presetHeaders, ...caseHeaders };
      const result = await fetchApiMonitorProxy({
        method: record.method,
        url,
        headers,
        body: ['POST', 'PUT', 'PATCH'].includes(record.method) ? record.request_body || undefined : undefined,
      });
      const statusPass = result.status_code === record.expected_status;
      const bodyText = formatProxyResponseBody(result.body);
      const assertResult = evaluateResponseAssert({
        mode: record.response_assert_mode,
        expectedResponse: record.expected_response,
        rulesRaw: record.response_assert_rules,
        actualBody: result.body,
      });
      const pass = statusPass && assertResult.pass;
      const detailParts: string[] = [];
      if (!statusPass) {
        detailParts.push(`状态码：预期 ${record.expected_status}，实际 ${result.status_code}`);
      }
      if (!assertResult.pass) {
        detailParts.push(assertResult.failures.join('；') || assertResult.message);
      }
      const detail = pass
        ? `状态码与响应断言均通过（${result.status_code}）`
        : detailParts.join('；') || '执行未通过';
      const saved = await saveApiTestCaseExecutionResult(record.id, {
        passed: pass,
        status_code: result.status_code,
        response: bodyText,
        detail,
      });
      patchCaseInList(saved);
      setExecuteResult({
        caseName: record.name,
        pass,
        statusCode: result.status_code,
        body: bodyText,
        detail,
      });
    } catch (error) {
      const detail = getApiErrorMessage(error, '执行失败');
      try {
        const saved = await saveApiTestCaseExecutionResult(record.id, {
          passed: false,
          detail: String(detail),
        });
        patchCaseInList(saved);
      } catch {
        // ignore persistence failure
      }
      appMessage.error(detail);
    } finally {
      setExecutingId(null);
    }
  }, [appMessage, envPreset, patchCaseInList]);

  const handleSubmit = async (values: ApiTestCaseFormValues) => {
    try {
      const payload = {
        ...values,
        endpoint_id: endpoint.id,
      };
      if (editing) {
        await updateApiTestCase(editing.id, payload);
        appMessage.success('更新成功');
      } else {
        await createApiTestCase(payload);
        appMessage.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      setVisible(true);
      await loadCases();
    } catch (error) {
      showApiError(error, '保存失败');
      throw new Error('save failed');
    }
  };

  const columns = useMemo<ColumnsType<ApiTestCase>>(
    () => [
      {
        title: '序号',
        width: 70,
        render: (_value, _record, index) => index + 1,
      },
      {
        title: '用例名称',
        dataIndex: 'name',
        width: 180,
        render: (value) => ellipsisCell(value, 160),
      },
      {
        title: '请求方式',
        dataIndex: 'method',
        width: 90,
      },
      {
        title: '请求参数',
        dataIndex: 'request_params',
        width: 160,
        render: (value) => ellipsisCell(value, 140),
      },
      {
        title: '请求数据',
        dataIndex: 'request_body',
        width: 160,
        render: (value) => ellipsisCell(value, 140),
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
        key: 'execute_status',
        width: 100,
        align: 'center',
        render: (_value, record) => renderCaseExecuteStatusCell(record),
      },
      {
        title: '操作',
        key: 'actions',
        width: 180,
        fixed: 'right',
        render: (_, record) => (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => openCreate()}>
              新增
            </Button>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Popconfirm title="确认删除该用例？" onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
            <Button
              type="link"
              size="small"
              icon={<PlayCircleOutlined />}
              loading={executingId === record.id}
              onClick={() => handleExecute(record)}
            >
              执行
            </Button>
          </Space>
        ),
      },
    ],
    [executingId, openCreate, openEdit, handleDelete, handleExecute],
  );

  return (
    <div className="api-monitor-doc__section api-monitor-endpoint-cases">
      <Space wrap>
        <Button type="primary" loading={generating} onClick={handleGenerate}>
          用例生成
        </Button>
        {visible ? (
          <Button icon={<PlusOutlined />} onClick={openCreate} disabled={!contextReady}>
            新增用例
          </Button>
        ) : null}
      </Space>

      {visible ? (
        <Table
          className="api-monitor-endpoint-cases__table"
          size="small"
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={cases}
          pagination={false}
          scroll={{ x: 1300 }}
          locale={{ emptyText: '暂无关联用例，可点击「用例生成」自动创建冒烟用例' }}
        />
      ) : null}

      <ApiCaseFormModal
        open={modalOpen}
        editing={editing}
        projectOptions={projectOptions}
        environmentOptions={environmentOptions}
        initialValues={editing ? undefined : caseDefaults ?? undefined}
        hideContextFields
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />

      <Modal
        title={executeResult ? `执行结果 · ${executeResult.caseName}` : '执行结果'}
        open={executeResult != null}
        onCancel={() => setExecuteResult(null)}
        footer={null}
        width={760}
        destroyOnHidden
      >
        {executeResult ? (
          <div className="api-monitor-endpoint-cases__execute-result">
            <Typography.Paragraph type={executeResult.pass ? 'success' : 'danger'}>
              {executeResult.detail}
            </Typography.Paragraph>
            <Typography.Text type="secondary">实际状态码：{executeResult.statusCode}</Typography.Text>
            <pre className="api-monitor-endpoint-cases__execute-body">{executeResult.body || '（空响应）'}</pre>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
