import { App, Button, Input, Select, Space, Typography } from 'antd';
import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { fetchApiMonitorProxy } from '../../api';
import type { ApiMonitorEndpoint, ApiMonitorParameter } from '../../types/apiMonitor';
import type { ApiMonitorEnvPreset } from './apiMonitorEnvPreset';
import { formatDebugHeadersText } from './apiMonitorEnvPreset';
import {
  buildDebugRequestBody,
  buildDebugUrl,
  inferGatewayPathPrefix,
  statusHint,
} from './debugUtils';

interface ApiMonitorDebugPanelProps {
  endpoint: ApiMonitorEndpoint;
  envPreset: ApiMonitorEnvPreset;
}

function defaultValueForType(dataType: string): string {
  const lower = dataType.toLowerCase();
  if (lower.includes('int') || lower.includes('number')) return '0';
  if (lower.includes('bool')) return 'false';
  if (lower.includes('array') || lower.includes('list')) return '[]';
  if (lower.includes('object') || lower.includes('dict')) return '{}';
  return '';
}

export default function ApiMonitorDebugPanel({ endpoint, envPreset }: ApiMonitorDebugPanelProps) {
  const { message } = App.useApp();
  const [pathPrefix, setPathPrefix] = useState('');
  const [pathValues, setPathValues] = useState<Record<string, string>>({});
  const [queryValues, setQueryValues] = useState<Record<string, string>>({});
  const [requestUrl, setRequestUrl] = useState('');
  const [urlManuallyEdited, setUrlManuallyEdited] = useState(false);
  const [bodyText, setBodyText] = useState('{}');
  const [headersText, setHeadersText] = useState(formatDebugHeadersText(envPreset));
  const [loading, setLoading] = useState(false);
  const [responseText, setResponseText] = useState('');
  const [statusCode, setStatusCode] = useState<number | null>(null);

  const pathParams = useMemo(
    () => endpoint.parameters.filter((item) => item.in === 'path'),
    [endpoint.parameters],
  );
  const queryParams = useMemo(
    () => endpoint.parameters.filter((item) => item.in === 'query'),
    [endpoint.parameters],
  );
  const bodyParams = useMemo(
    () => endpoint.parameters.filter((item) => item.in === 'body'),
    [endpoint.parameters],
  );

  const autoRequestUrl = useMemo(
    () =>
      buildDebugUrl(
        envPreset.serverAddress,
        pathPrefix,
        endpoint.path,
        pathValues,
        queryValues,
      ),
    [endpoint.path, envPreset.serverAddress, pathPrefix, pathValues, queryValues],
  );

  useEffect(() => {
    setPathPrefix(inferGatewayPathPrefix(endpoint));
    setUrlManuallyEdited(false);

    const nextPath: Record<string, string> = {};
    for (const param of pathParams) {
      nextPath[param.name] = defaultValueForType(param.data_type);
    }
    setPathValues(nextPath);

    const nextQuery: Record<string, string> = {};
    for (const param of queryParams) {
      nextQuery[param.name] = defaultValueForType(param.data_type);
    }
    setQueryValues(nextQuery);
    setBodyText(buildDebugRequestBody(bodyParams));
    setResponseText('');
    setStatusCode(null);
  }, [endpoint.id, pathParams, queryParams, bodyParams, endpoint.tags]);

  useEffect(() => {
    setHeadersText(formatDebugHeadersText(envPreset));
    setUrlManuallyEdited(false);
  }, [envPreset]);

  useEffect(() => {
    if (!urlManuallyEdited) {
      setRequestUrl(autoRequestUrl);
    }
  }, [autoRequestUrl, urlManuallyEdited]);

  const responseHint = useMemo(
    () => (statusCode != null ? statusHint(statusCode, pathPrefix) : null),
    [pathPrefix, statusCode],
  );

  const updateParam = (
    setter: Dispatch<SetStateAction<Record<string, string>>>,
    name: string,
    value: string,
  ) => {
    setter((prev) => ({ ...prev, [name]: value }));
  };

  const handleSend = async () => {
    setLoading(true);
    setResponseText('');
    setStatusCode(null);
    try {
      let headers: Record<string, string> = {};
      if (headersText.trim()) {
        headers = JSON.parse(headersText) as Record<string, string>;
      }
      const result = await fetchApiMonitorProxy({
        method: endpoint.method,
        url: requestUrl,
        headers,
        body: ['POST', 'PUT', 'PATCH'].includes(endpoint.method) ? bodyText : undefined,
      });
      setStatusCode(result.status_code);
      try {
        setResponseText(JSON.stringify(JSON.parse(result.body), null, 2));
      } catch {
        setResponseText(result.body);
      }
    } catch (error) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (error instanceof Error ? error.message : '请求失败');
      message.error(detail);
    } finally {
      setLoading(false);
    }
  };

  const renderParamFields = (
    title: string,
    params: ApiMonitorParameter[],
    values: Record<string, string>,
    onChange: (name: string, value: string) => void,
  ) => {
    if (!params.length) return null;
    return (
      <div className="api-monitor-debug__block">
        <Typography.Text strong>{title}</Typography.Text>
        <div className="api-monitor-debug__fields">
          {params.map((param) => (
            <div key={param.name} className="api-monitor-debug__field">
              <label>
                {param.name}
                {param.required ? <span className="api-monitor-debug__required">*</span> : null}
                <Typography.Text type="secondary"> ({param.data_type})</Typography.Text>
              </label>
              <Input
                value={values[param.name] ?? ''}
                onChange={(event) => onChange(param.name, event.target.value)}
              />
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="api-monitor-debug">
      <div className="api-monitor-debug__block">
        <Typography.Text strong>路径前缀</Typography.Text>
        <Input
          value={pathPrefix}
          onChange={(event) => setPathPrefix(event.target.value)}
          placeholder=""
        />
        <Typography.Paragraph type="secondary" className="api-monitor-debug__hint">
          可选。扫描路径已含网关前缀时留空；若仅为微服务内部路径，可在此补充，例如 /api/alarm。
        </Typography.Paragraph>
      </div>

      <div className="api-monitor-debug__block">
        <Typography.Text strong>请求地址</Typography.Text>
        <Input
          value={requestUrl}
          onChange={(event) => {
            setUrlManuallyEdited(true);
            setRequestUrl(event.target.value);
          }}
          placeholder="http://host:port/api/..."
        />
        <Typography.Paragraph type="secondary" className="api-monitor-debug__hint">
          默认拼接环境预置中的服务器地址（{envPreset.serverAddress || '未配置'}），支持手动修改。
        </Typography.Paragraph>
      </div>

      <div className="api-monitor-debug__block">
        <Typography.Text strong>请求类型</Typography.Text>
        <Select
          value={endpoint.method}
          options={[{ value: endpoint.method, label: endpoint.method }]}
          disabled
          style={{ width: 120 }}
        />
      </div>

      {renderParamFields('Path 参数', pathParams, pathValues, (name, value) =>
        updateParam(setPathValues, name, value),
      )}
      {renderParamFields('Query 参数', queryParams, queryValues, (name, value) =>
        updateParam(setQueryValues, name, value),
      )}

      {['POST', 'PUT', 'PATCH'].includes(endpoint.method) ? (
        <div className="api-monitor-debug__block">
          <Typography.Text strong>请求体</Typography.Text>
          <Input.TextArea value={bodyText} onChange={(event) => setBodyText(event.target.value)} rows={8} />
          {bodyParams[0]?.schema_name ? (
            <Typography.Paragraph type="secondary" className="api-monitor-debug__hint">
              Spring @RequestBody 直接传对象 JSON，类型：{bodyParams[0].schema_name}
            </Typography.Paragraph>
          ) : null}
        </div>
      ) : null}

      <div className="api-monitor-debug__block">
        <Typography.Text strong>请求头</Typography.Text>
        <Input.TextArea
          value={headersText}
          onChange={(event) => setHeadersText(event.target.value)}
          rows={4}
        />
      </div>

      <Space>
        <Button type="primary" loading={loading} onClick={handleSend}>
          发送请求
        </Button>
        {statusCode != null ? <Typography.Text>状态码：{statusCode}</Typography.Text> : null}
      </Space>

      {responseHint ? (
        <Typography.Paragraph type="warning" className="api-monitor-debug__hint">
          {responseHint}
        </Typography.Paragraph>
      ) : null}

      <div className="api-monitor-debug__block">
        <Typography.Text strong>响应内容</Typography.Text>
        <pre className="api-monitor-debug__response">{responseText || '（暂无响应）'}</pre>
      </div>
    </div>
  );
}
