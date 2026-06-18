import { ApiOutlined } from '@ant-design/icons';
import { App, Button, Form, Input, InputNumber, Modal } from 'antd';
import { useCallback, useMemo, useState } from 'react';
import { testMqttConsoleConnection } from '../api';
import type { MqttConsoleConnection, MqttConsoleConnectionFormValues } from '../types';
import './ConnectionFormModal.css';

interface Props {
  open: boolean;
  connection?: MqttConsoleConnection | null;
  onCancel: () => void;
  onSubmit: (values: MqttConsoleConnectionFormValues) => Promise<void>;
}

const formLayout = {
  labelCol: { flex: '84px' },
  wrapperCol: { flex: 'auto' },
};

export default function MqttConsoleConnectionModal({
  open,
  connection,
  onCancel,
  onSubmit,
}: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<MqttConsoleConnectionFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);

  const formKey = connection ? `edit-${connection.id}` : 'create';

  const initialValues = useMemo<MqttConsoleConnectionFormValues>(
    () =>
      connection
        ? {
            name: connection.name,
            host: connection.host,
            port: connection.port,
            username: connection.username ?? '',
            password: '',
          }
        : {
            name: '',
            host: '',
            port: 1883,
            username: '',
            password: '',
          },
    [connection],
  );

  const fillFormValues = useCallback(() => {
    if (connection) {
      form.setFieldsValue({
        name: connection.name,
        host: connection.host,
        port: connection.port,
        username: connection.username ?? '',
        password: '',
      });
      return;
    }
    form.resetFields();
    form.setFieldsValue({ port: 1883 });
  }, [connection, form]);

  const handleTest = async () => {
    const values = await form.validateFields(['host', 'port', 'username', 'password']);
    setTesting(true);
    try {
      const result = await testMqttConsoleConnection({
        host: values.host?.trim() ?? '',
        port: Number(values.port) || 1883,
        username: values.username?.trim() || undefined,
        password: values.password?.trim() || undefined,
      });
      if (result.ok) {
        message.success(
          result.latency_ms != null ? `${result.message}（${result.latency_ms}ms）` : result.message,
        );
      } else {
        message.error(result.message);
      }
    } catch {
      message.error('测试连接失败');
    } finally {
      setTesting(false);
    }
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    const payload: MqttConsoleConnectionFormValues = {
      name: values.name.trim(),
      host: values.host.trim(),
      port: Number(values.port) || 1883,
      username: values.username?.trim() || undefined,
    };
    const password = values.password?.trim();
    if (password || !connection?.password_set) {
      payload.password = password || undefined;
    }
    setSubmitting(true);
    try {
      await onSubmit(payload);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={connection ? '编辑 MQTT 连接' : '新增 MQTT 连接'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={submitting}
      destroyOnHidden
      afterOpenChange={(visible) => {
        if (visible) {
          fillFormValues();
        }
      }}
      width={520}
      className="connection-form-modal"
    >
      <Form
        key={open ? formKey : 'closed'}
        form={form}
        {...formLayout}
        layout="horizontal"
        initialValues={initialValues}
      >
        <Form.Item
          name="name"
          label="连接名称"
          rules={[{ required: true, message: '请输入连接名称' }]}
        >
          <Input placeholder="例如：生产 MQTT Broker" />
        </Form.Item>
        <Form.Item
          name="host"
          label="Broker 地址"
          rules={[{ required: true, message: '请输入 Broker 地址' }]}
          extra="仅 IP 或域名，连接格式为 mqtt://主机:端口"
        >
          <Input placeholder="10.100.0.230" />
        </Form.Item>
        <Form.Item
          name="port"
          label="端口"
          rules={[{ required: true, message: '请输入端口' }]}
        >
          <InputNumber min={1} max={65535} className="connection-form-modal__port" />
        </Form.Item>
        <Form.Item name="username" label="用户名">
          <Input placeholder="可选" />
        </Form.Item>
        <Form.Item name="password" label="密码">
          <Input.Password
            placeholder={connection?.password_set ? '已设置，留空不修改' : '可选'}
            autoComplete="new-password"
          />
        </Form.Item>
        <div className="connection-form-modal__test-btn">
          <Button icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
            测试连接
          </Button>
        </div>
      </Form>
    </Modal>
  );
}
