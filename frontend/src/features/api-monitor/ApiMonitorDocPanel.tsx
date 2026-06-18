import { Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo } from 'react';
import type { ApiMonitorEndpoint, ApiMonitorParameter } from '../../types/apiMonitor';


const METHOD_COLORS: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'gold',
  DELETE: 'red',
  HEAD: 'default',
  OPTIONS: 'default',
};

const PARAM_IN_LABELS: Record<string, string> = {
  query: 'query',
  path: 'path',
  body: 'body',
  header: 'header',
  formData: 'formData',
};

interface ApiMonitorDocPanelProps {
  endpoint: ApiMonitorEndpoint;
}

type FlatParameter = ApiMonitorParameter & { rowKey: string };
type TreeParameter = ApiMonitorParameter & { rowKey: string; children?: TreeParameter[] };

function buildParameterTree(parameters: ApiMonitorParameter[], prefix = ''): TreeParameter[] {
  return parameters.map((param, index) => {
    const rowKey = `${prefix}${param.in}-${param.name}-${index}`;
    const node: TreeParameter = { ...param, rowKey };
    if (param.children?.length) {
      node.children = buildParameterTree(param.children, `${rowKey}-`);
    }
    return node;
  });
}

function hasParameterDescription(parameters: ApiMonitorParameter[]): boolean {
  return parameters.some((param) => {
    if (param.description?.trim()) {
      return true;
    }
    return Boolean(param.children?.length && hasParameterDescription(param.children));
  });
}

function flattenParameters(parameters: ApiMonitorParameter[], prefix = ''): FlatParameter[] {
  const rows: FlatParameter[] = [];
  parameters.forEach((param, index) => {
    const rowKey = `${prefix}${param.in}-${param.name}-${index}`;
    rows.push({ ...param, rowKey });
    if (param.children?.length) {
      rows.push(...flattenParameters(param.children, `${rowKey}-`));
    }
  });
  return rows;
}

function defaultValueForType(dataType: string): unknown {
  const lower = dataType.toLowerCase();
  if (lower.includes('int') || lower.includes('long') || lower.includes('number')) return 0;
  if (lower.includes('bool')) return false;
  if (lower.includes('array') || lower.includes('list')) return [];
  if (lower.includes('object') || lower.includes('dict')) return {};
  if (lower.includes('string') || lower === 'string') return '';
  return '';
}

function buildBodySample(param: ApiMonitorParameter): unknown {
  if (param.children?.length) {
    const sample: Record<string, unknown> = {};
    for (const child of param.children) {
      sample[child.name] = defaultValueForType(child.data_type);
    }
    return sample;
  }
  if (param.schema_name && (param.data_type === 'object' || param.in === 'body')) {
    return {};
  }
  return defaultValueForType(param.data_type);
}

function buildRequestExample(endpoint: ApiMonitorEndpoint): string {
  const parts: string[] = [];
  const queryParams = endpoint.parameters.filter((item) => item.in === 'query');
  const pathParams = endpoint.parameters.filter((item) => item.in === 'path');
  const bodyParams = endpoint.parameters.filter((item) => item.in === 'body');
  const formParams = endpoint.parameters.filter((item) => item.in === 'formData');

  let path = endpoint.path;
  for (const param of pathParams) {
    const sample = encodeURIComponent(String(defaultValueForType(param.data_type)));
    path = path.replace(`{${param.name}}`, sample);
  }

  if (queryParams.length > 0) {
    const query = queryParams
      .map((param) => `${param.name}=${encodeURIComponent(String(defaultValueForType(param.data_type)))}`)
      .join('&');
    parts.push(`${path}?${query}`);
  } else if (pathParams.length > 0) {
    parts.push(path);
  }

  if (bodyParams.length > 0) {
    if (bodyParams.length === 1) {
      parts.push(JSON.stringify(buildBodySample(bodyParams[0]), null, 2));
    } else {
      const sample: Record<string, unknown> = {};
      for (const param of bodyParams) {
        sample[param.name] = buildBodySample(param);
      }
      parts.push(JSON.stringify(sample, null, 2));
    }
  }

  if (formParams.length > 0) {
    const sample: Record<string, unknown> = {};
    for (const param of formParams) {
      sample[param.name] = defaultValueForType(param.data_type);
    }
    parts.push(JSON.stringify(sample, null, 2));
  }

  return parts.join('\n\n');
}

export default function ApiMonitorDocPanel({ endpoint }: ApiMonitorDocPanelProps) {
  const requestTree = useMemo(() => buildParameterTree(endpoint.parameters), [endpoint.parameters]);
  const requestExample = useMemo(() => buildRequestExample(endpoint), [endpoint]);
  const hasParamDescription = hasParameterDescription(endpoint.parameters);
  const author = endpoint.source?.author;
  const authoredAt = endpoint.source?.authored_at;

  const requestColumns: ColumnsType<TreeParameter> = [
    { title: '参数名称', dataIndex: 'name', width: 200 },
    {
      title: '参数说明',
      dataIndex: 'description',
      ellipsis: true,
      render: (value?: string) => value?.trim() || '—',
    },
    {
      title: '请求类型',
      dataIndex: 'in',
      width: 90,
      render: (value: string) => PARAM_IN_LABELS[value] || value || '-',
    },
    {
      title: '是否必须',
      dataIndex: 'required',
      width: 90,
      render: (value: boolean) => (
        <Tag color={value ? 'red' : 'default'}>{value ? 'true' : 'false'}</Tag>
      ),
    },
    { title: '数据类型', dataIndex: 'data_type', width: 140 },
    {
      title: 'Schema',
      dataIndex: 'schema_name',
      width: 140,
      render: (value?: string | null) => value || '-',
    },
  ];

  const responseRows = useMemo(() => {
    const successResponse =
      endpoint.responses.find((response) => response.status_code === '200') ?? endpoint.responses[0];
    if (!successResponse) {
      return [];
    }
    const props = successResponse.properties?.length
      ? flattenParameters(successResponse.properties, 'resp-')
      : successResponse.schema_name
        ? [
            {
              rowKey: 'resp-schema',
              name: '(response)',
              in: 'body',
              required: true,
              data_type: successResponse.data_type || 'object',
              description: successResponse.description || '',
              schema_name: successResponse.schema_name,
            },
          ]
        : [];
    return props;
  }, [endpoint.responses]);

  const responseColumns: ColumnsType<FlatParameter> = [
    { title: '参数名称', dataIndex: 'name', width: 160 },
    {
      title: '参数说明',
      dataIndex: 'description',
      ellipsis: true,
      render: (value?: string) => value?.trim() || '—',
    },
    { title: '类型', dataIndex: 'data_type', width: 160 },
    {
      title: 'schema',
      dataIndex: 'schema_name',
      width: 140,
      render: (value?: string | null) => value || '-',
    },
  ];

  return (
    <div className="api-monitor-doc">
      <div className="api-monitor-doc__header">
        <Space size={12} align="center" wrap>
          <Tag color={METHOD_COLORS[endpoint.method] || 'default'} className="api-monitor-doc__method">
            {endpoint.method}
          </Tag>
          <Typography.Title level={4} className="api-monitor-doc__title">
            {endpoint.summary}
          </Typography.Title>
          {author ? (
            <Typography.Text type="secondary" className="api-monitor-doc__author">
              {author}
              {authoredAt ? ` · ${authoredAt}` : ''}
            </Typography.Text>
          ) : null}
        </Space>
        <Typography.Text code className="api-monitor-doc__path">
          {endpoint.path}
        </Typography.Text>
      </div>

      <div className="api-monitor-doc__section">
        <div className="api-monitor-doc__meta-row">
          <span>请求数据类型</span>
          <strong>{endpoint.request_content_type || '-'}</strong>
        </div>
        <div className="api-monitor-doc__meta-row">
          <span>响应数据类型</span>
          <strong>{endpoint.response_content_type || '*/*'}</strong>
        </div>
      </div>

      <div className="api-monitor-doc__section">
        <Typography.Text strong>请求示例</Typography.Text>
        {requestExample ? (
          <pre className="api-monitor-doc__code">{requestExample}</pre>
        ) : (
          <Typography.Text type="secondary">
            无请求体或查询参数示例；GET 且无标注参数的接口通常属于正常情况。
          </Typography.Text>
        )}
      </div>

      <div className="api-monitor-doc__section">
        <Typography.Text strong>请求参数</Typography.Text>
        {!hasParamDescription && requestTree.length > 0 ? (
          <Typography.Paragraph type="secondary" className="api-monitor-doc__hint">
            源码中未标注 @ApiOperation(notes) 或参数注释，因此暂无参数说明；这在内网老项目中较常见。
          </Typography.Paragraph>
        ) : null}
        <Table
          size="small"
          rowKey="rowKey"
          columns={requestColumns}
          dataSource={requestTree}
          pagination={false}
          expandable={{
            defaultExpandAllRows: true,
            indentSize: 20,
            expandIcon: ({ expanded, onExpand, record }) => {
              if (!record.children?.length) {
                return <span className="api-monitor-doc__expand-placeholder" />;
              }
              return (
                <button
                  type="button"
                  className="api-monitor-doc__expand-btn"
                  aria-label={expanded ? '收起' : '展开'}
                  onClick={(event) => onExpand(record, event)}
                >
                  {expanded ? '−' : '+'}
                </button>
              );
            },
          }}
          locale={{ emptyText: '无请求参数' }}
          scroll={{ x: 900 }}
        />
      </div>

      <div className="api-monitor-doc__section">
        <Typography.Text strong>响应状态</Typography.Text>
        <div className="api-monitor-doc__status-list">
          {endpoint.responses.map((response) => (
            <div key={response.status_code} className="api-monitor-doc__status-item">
              <Tag color="success">{response.status_code}</Tag>
              <span>{response.description || '成功'}</span>
              {response.schema_name ? (
                <Typography.Text type="secondary">（{response.schema_name}）</Typography.Text>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      <div className="api-monitor-doc__section">
        <Typography.Text strong>响应参数</Typography.Text>
        <Table
          size="small"
          rowKey="rowKey"
          columns={responseColumns}
          dataSource={responseRows}
          pagination={false}
          expandable={{ childrenColumnName: '_childrenDisabled' }}
          locale={{ emptyText: '无响应参数定义' }}
          scroll={{ x: 900 }}
        />
      </div>

      {endpoint.source?.file ? (
        <div className="api-monitor-doc__source">
          来源：{endpoint.source.file}
          {endpoint.source.line ? `:${endpoint.source.line}` : ''}
        </div>
      ) : null}
    </div>
  );
}
