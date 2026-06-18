import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { App, Button, Modal, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { formatCaseHeadersDisplay, formatCaseRequestParamsDisplay, resolveCaseHeaders } from '../../utils/caseRequestParts';
import { evaluateResponseAssert, formatExpectedResponseDisplay } from '../../utils/responseAssert';
import {
  formatProxyResponseBody,
  renderCaseExecuteStatusCell,
} from '../../utils/caseExecuteStatus';
import { buildDebugUrl } from './debugUtils';
import { distributeColumnWidths, useContainerWidth } from '../../hooks/useContainerWidth';

const METHOD_COLORS: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'gold',
  DELETE: 'red',
  HEAD: 'default',
  OPTIONS: 'default',
};

const CASE_TABLE_ACTIONS_WIDTH = 168;
const CASE_TABLE_COLUMN_WEIGHTS = [6, 24, 6, 13, 13, 7, 22, 9];

interface ApiMonitorCasesPanelProps {
  endpoint: ApiMonitorEndpoint;
  projectId?: number;
  environmentId?: number;
  service?: string | null;
  envPreset: ApiMonitorEnvPreset;
  projectOptions: Array<{ value: number; label: string }>;
  environmentOptions: Array<{ value: number; label: string }>;
}

function ellipsisCell(value?: string | null, maxWidth?: number) {
  if (!value) {
    return '-';
  }
  return (
    <Typography.Text
      ellipsis={{ tooltip: value }}
      style={maxWidth ? { maxWidth: Math.max(40, maxWidth - 16) } : { width: '100%' }}
    >
      {value}
    </Typography.Text>
  );
}

export default function ApiMonitorCasesPanel({
  endpoint,
  projectId,
  environmentId,
  service,
  envPreset,
  projectOptions,
  environmentOptions,
}: ApiMonitorCasesPanelProps) {
  const { message: appMessage, modal } = App.useApp();
  const tableWrapRef = useRef<HTMLDivElement>(null);
  const tableWidth = useContainerWidth(tableWrapRef);
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

  const activeCases = useMemo(
    () => cases.filter((item) => item.status !== 'deleted'),
    [cases],
  );

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
        page_size: 100,
      });
      setCases(result.items.filter((item) => item.status !== 'deleted'));
    } catch {
      appMessage.error('加载关联用例失败');
    } finally {
      setLoading(false);
    }
  }, [appMessage, endpoint.id]);

  useEffect(() => {
    setCases([]);
    setEditing(null);
    setModalOpen(false);
    setExecuteResult(null);
    loadCases();
  }, [endpoint.id, loadCases]);

  const runGenerate = useCallback(async (overwrite: boolean) => {
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
        overwrite,
      });
      await loadCases();
      if (result.created > 0) {
        if (result.overwritten && result.overwritten > 0) {
          appMessage.success(`已覆盖 ${result.overwritten} 条用例，并生成 ${result.created} 条新用例`);
        } else {
          appMessage.success(`已生成 ${result.created} 条冒烟用例`);
        }
      }
    } catch (error) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (error instanceof Error ? error.message : '用例生成失败');
      appMessage.error(String(detail));
    } finally {
      setGenerating(false);
    }
  }, [
    appMessage,
    contextReady,
    endpoint.id,
    endpoint.method,
    endpoint.parameters,
    endpoint.path,
    endpoint.summary,
    environmentId,
    loadCases,
    projectId,
    service,
  ]);

  const handleGenerate = useCallback(() => {
    if (!contextReady) {
      appMessage.warning('请先选择项目、环境和服务');
      return;
    }
    if (activeCases.length > 0) {
      modal.confirm({
        title: '覆盖已有用例',
        content: `该接口已有 ${activeCases.length} 条用例，AI 重新生成将覆盖现有用例，是否继续？`,
        okText: '确认覆盖',
        cancelText: '取消',
        centered: true,
        onOk: () => runGenerate(true),
      });
      return;
    }
    void runGenerate(false);
  }, [activeCases.length, appMessage, contextReady, modal, runGenerate]);

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
      setCases((prev) => prev.filter((item) => item.id !== id));
      appMessage.success('删除成功');
      await loadCases();
    } catch {
      appMessage.error('删除失败');
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
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (error instanceof Error ? error.message : '执行失败');
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
      await loadCases();
    } catch {
      appMessage.error('保存失败');
      throw new Error('save failed');
    }
  };

  const columnWidths = useMemo(
    () => distributeColumnWidths(tableWidth, CASE_TABLE_COLUMN_WEIGHTS, CASE_TABLE_ACTIONS_WIDTH),
    [tableWidth],
  );

  const columns = useMemo<ColumnsType<ApiTestCase>>(
    () => {
      const [
        indexWidth = 70,
        nameWidth = 260,
        methodWidth = 72,
        headersWidth = 150,
        paramsWidth = 150,
        statusWidth = 88,
        responseWidth = 170,
        executeWidth = 88,
      ] = columnWidths;

      return [
      {
        title: '序号',
        width: indexWidth,
        render: (_value, _record, index) => index + 1,
      },
      {
        title: '用例名称',
        dataIndex: 'name',
        width: nameWidth,
        ellipsis: true,
        render: (value) => ellipsisCell(value, nameWidth),
      },
      {
        title: '请求方式',
        dataIndex: 'method',
        width: methodWidth,
        align: 'center',
      },
      {
        title: '请求头',
        dataIndex: 'request_headers',
        width: headersWidth,
        ellipsis: true,
        render: (_value, record) =>
          ellipsisCell(
            formatCaseHeadersDisplay(record.request_headers, record.request_params),
            headersWidth,
          ),
      },
      {
        title: '请求参数',
        dataIndex: 'request_body',
        width: paramsWidth,
        ellipsis: true,
        render: (_value, record) =>
          ellipsisCell(
            formatCaseRequestParamsDisplay(record.request_params, record.request_body),
            paramsWidth,
          ),
      },
      {
        title: '预期响应码',
        dataIndex: 'expected_status',
        width: statusWidth,
        align: 'center',
      },
      {
        title: '预期响应结果',
        dataIndex: 'expected_response',
        width: responseWidth,
        ellipsis: true,
        render: (_value, record) =>
          ellipsisCell(
            formatExpectedResponseDisplay(
              record.response_assert_mode,
              record.expected_response,
              record.response_assert_rules,
            ),
            responseWidth,
          ),
      },
      {
        title: '执行状态',
        key: 'execute_status',
        width: executeWidth,
        align: 'center',
        render: (_value, record) => renderCaseExecuteStatusCell(record),
      },
      {
        title: '操作',
        key: 'actions',
        width: CASE_TABLE_ACTIONS_WIDTH,
        fixed: 'right',
        render: (_, record) => (
          <Space size={4}>
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
    ];
    },
    [columnWidths, executingId, handleDelete, handleExecute, openEdit],
  );

  return (
    <div className="api-monitor-cases">
      <div className="api-monitor-cases__header">
        <Space size={12} align="center" wrap>
          <Tag color={METHOD_COLORS[endpoint.method] || 'default'} className="api-monitor-doc__method">
            {endpoint.method}
          </Tag>
          <Typography.Title level={4} className="api-monitor-doc__title">
            {endpoint.summary}
          </Typography.Title>
        </Space>
        <Typography.Text code className="api-monitor-doc__path">
          {endpoint.path}
        </Typography.Text>
      </div>

      <div className="api-monitor-cases__toolbar">
        <Space wrap>
          <Button type="primary" loading={generating} onClick={handleGenerate}>
            AI用例生成
          </Button>
          <Button icon={<PlusOutlined />} onClick={openCreate} disabled={!contextReady}>
            新增用例
          </Button>
        </Space>
        {!contextReady ? (
          <Typography.Text type="secondary">请先选择项目、环境和服务后再生成或新增用例</Typography.Text>
        ) : null}
      </div>

      <div ref={tableWrapRef} className="api-monitor-cases__table-wrap">
        <Table
          className="api-monitor-cases__table"
          size="small"
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={activeCases}
          pagination={false}
          tableLayout="fixed"
          scroll={tableWidth > 0 ? { x: tableWidth } : undefined}
          locale={{ emptyText: '暂无关联用例，可点击「AI用例生成」自动创建冒烟用例' }}
        />
      </div>

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
          <div className="api-monitor-cases__execute-result">
            <Typography.Paragraph type={executeResult.pass ? 'success' : 'danger'}>
              {executeResult.detail}
            </Typography.Paragraph>
            <Typography.Text type="secondary">实际状态码：{executeResult.statusCode}</Typography.Text>
            <pre className="api-monitor-cases__execute-body">{executeResult.body || '（空响应）'}</pre>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
