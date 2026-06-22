import { ApiOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Col, Form, Input, InputNumber, Modal, Popconfirm, Row, Space, Typography, message } from 'antd';
import type { AxiosError } from 'axios';
import { useEffect, useState } from 'react';
import {
  fetchSchemaMonitor,
  pingSchemaMonitor,
  resetSchemaMonitorBaseline,
  scanSchemaMonitor,
  updateSchemaMonitor,
} from '../api';
import type { SchemaMonitorStatus } from '../types';

interface Props {
  open: boolean;
  subscriptionId: number | null;
  connectionName?: string;
  onClose: () => void;
}

interface FormValues {
  host: string;
  port: number;
  username: string;
  password: string;
  include_databases: string;
  exclude_databases: string;
}

function joinList(values: string[] | undefined): string {
  return (values ?? []).join(', ');
}

function splitList(value: string | undefined): string[] {
  return (value ?? '')
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

const compactItem = { marginBottom: 10 };

export default function SchemaMonitorModal({
  open,
  subscriptionId,
  connectionName,
  onClose,
}: Props) {
  const [form] = Form.useForm<FormValues>();
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [status, setStatus] = useState<SchemaMonitorStatus | null>(null);

  const buildConnectionPayload = (values: FormValues) => {
    const host = values.host.trim();
    const username = values.username.trim();
    const password = values.password.trim();
    if (!host || !username) {
      message.warning('请先填写 IP 和账号');
      return null;
    }
    return {
      host,
      port: values.port,
      username,
      ...(password ? { password } : {}),
    };
  };

  const loadStatus = async (id: number) => {
    setLoading(true);
    try {
      const data = await fetchSchemaMonitor(id);
      setStatus(data);
      form.setFieldsValue({
        host: data.host ?? '',
        port: data.port ?? 3306,
        username: data.username ?? '',
        password: '',
        include_databases: joinList(data.include_databases),
        exclude_databases: joinList(data.exclude_databases),
      });
    } catch {
      message.error('加载结构巡检配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && subscriptionId) {
      loadStatus(subscriptionId).catch(() => undefined);
    } else {
      setStatus(null);
      form.resetFields();
    }
  }, [open, subscriptionId, form]);

  const handleSave = async () => {
    if (!subscriptionId) return;
    const values = await form.validateFields();
    setLoading(true);
    try {
      const host = values.host.trim();
      const username = values.username.trim();
      const password = values.password.trim();
      const connectionChanged =
        host !== (status?.host ?? '') ||
        values.port !== (status?.port ?? 3306) ||
        username !== (status?.username ?? '') ||
        Boolean(password);

      const payload: {
        host?: string;
        port?: number;
        username?: string;
        password?: string;
        include_databases: string[];
        exclude_databases: string[];
      } = {
        include_databases: splitList(values.include_databases),
        exclude_databases: splitList(values.exclude_databases),
      };

      if (connectionChanged || !status?.connection_configured) {
        payload.host = host;
        payload.port = values.port;
        payload.username = username;
        if (password) {
          payload.password = password;
        }
      }

      const data = await updateSchemaMonitor(subscriptionId, payload);
      setStatus(data);
      form.setFieldValue('password', '');
      message.success('已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handlePing = async () => {
    if (!subscriptionId) return;
    const values = await form.validateFields(['host', 'port', 'username', 'password']);
    const connection = buildConnectionPayload(values);
    if (!connection) return;

    setPinging(true);
    try {
      const result = await pingSchemaMonitor(subscriptionId, connection);
      if (result.ok) {
        message.success(
          result.latency_ms != null
            ? `${result.message}（${result.latency_ms}ms）`
            : result.message,
        );
      } else {
        message.error(result.message);
      }
    } catch {
      message.error('连通性测试失败');
    } finally {
      setPinging(false);
    }
  };

  const extractErrorMessage = (error: unknown, fallback: string) => {
    const axiosError = error as AxiosError<{ detail?: string }>;
    const detail = axiosError.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (axiosError.code === 'ECONNABORTED') {
      return '巡检超时，库表较多时请稍候再试或缩小监控范围';
    }
    return fallback;
  };

  const handleScan = async () => {
    if (!subscriptionId) return;
    if (!status?.connection_configured) {
      message.warning('请先保存数据库连接配置');
      return;
    }
    if (!status.enabled) {
      message.warning('请先在订阅列表中启用该连接');
      return;
    }

    const hide = message.loading('巡检中，库表较多时可能需要几十秒...', 0);
    setScanning(true);
    try {
      const result = await scanSchemaMonitor(subscriptionId);
      message.success(result.message);
      await loadStatus(subscriptionId);
    } catch (error) {
      message.error(extractErrorMessage(error, '巡检失败'));
    } finally {
      hide();
      setScanning(false);
    }
  };

  const handleResetBaseline = async () => {
    if (!subscriptionId) return;
    const hide = message.loading('正在清除结构变更日志并重建基准...', 0);
    setResetting(true);
    try {
      const result = await resetSchemaMonitorBaseline(subscriptionId);
      message.success(result.message);
      await loadStatus(subscriptionId);
    } catch (error) {
      message.error(extractErrorMessage(error, '重置基准失败'));
    } finally {
      hide();
      setResetting(false);
    }
  };

  return (
    <Modal
      title={`结构巡检 · ${connectionName ?? ''}`}
      open={open}
      onCancel={onClose}
      width={480}
      styles={{ body: { paddingTop: 12 } }}
      footer={
        <Space size={8}>
          <Button size="small" onClick={onClose}>
            关闭
          </Button>
          <Button size="small" icon={<ApiOutlined />} loading={pinging} onClick={handlePing}>
            测试连接
          </Button>
          <Button size="small" icon={<ReloadOutlined />} loading={scanning} onClick={handleScan}>
            立即巡检
          </Button>
          <Popconfirm
            title="重置结构基准"
            description="将清除该订阅下所有结构变更日志，并以当前库表结构重新生成基准快照，是否继续？"
            okText="重置"
            cancelText="取消"
            onConfirm={() => handleResetBaseline()}
          >
            <Button size="small" danger loading={resetting}>
              重置基准
            </Button>
          </Popconfirm>
          <Button size="small" type="primary" loading={loading} onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
      destroyOnHidden
    >
      {status ? (
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 10, fontSize: 12 }}>
          每 {status.interval_seconds}s 巡检 · {status.database_count} 库 / {status.table_count} 表
          {status.last_scan_at ? ` · 上次 ${new Date(status.last_scan_at).toLocaleString()}` : ''}
          {status.last_error ? (
            <Typography.Text type="danger"> · {status.last_error}</Typography.Text>
          ) : null}
        </Typography.Text>
      ) : null}

      <Form form={form} layout="vertical" size="small" initialValues={{ port: 3306 }}>
        <Row gutter={8}>
          <Col span={16}>
            <Form.Item
              name="host"
              label="IP"
              style={compactItem}
              rules={[{ required: true, message: '必填' }]}
            >
              <Input placeholder="10.100.0.239" autoComplete="off" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="port"
              label="端口"
              style={compactItem}
              rules={[{ required: true, message: '必填' }]}
            >
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={8}>
          <Col span={12}>
            <Form.Item
              name="username"
              label="账号"
              style={compactItem}
              rules={[{ required: true, message: '必填' }]}
            >
              <Input placeholder="root" autoComplete="off" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="password"
              label="密码"
              style={compactItem}
              extra={status?.password_set ? '留空不改' : '可选，无密码可留空'}
            >
              <Input.Password placeholder="密码" autoComplete="new-password" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="include_databases" label="仅监控库" style={compactItem}>
          <Input placeholder="留空=全部，逗号分隔" />
        </Form.Item>
        <Form.Item name="exclude_databases" label="排除库" style={{ marginBottom: 0 }}>
          <Input placeholder="逗号分隔" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
